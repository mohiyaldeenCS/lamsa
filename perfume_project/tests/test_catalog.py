"""Catalog migration and behavior checks using disposable SQLite databases only."""
from decimal import Decimal
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from werkzeug.security import check_password_hash

from app import create_app
from catalog import CATEGORIES, AUDIENCES, IMAGES, VOLUMES, load_catalog, seed_catalog
from models import Order, OrderItem, Perfume, User, db


class CatalogLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.hidden, self.images = [], {}, []
        self.cards = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'a' and values.get('href'):
            self.links.append(values['href'])
        if tag == 'input' and values.get('type') == 'hidden':
            self.hidden[values.get('name')] = values.get('value')
        if tag == 'img':
            self.images.append(values.get('src'))
        if tag == 'article' and 'product-card' in values.get('class', '').split():
            self.cards += 1


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / 'catalog.db'
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        self.directory.cleanup()

    def make_app(self):
        app = create_app({'TESTING': True, 'SECRET_KEY': 'catalog-test-secret',
                          'WTF_CSRF_ENABLED': False,
                          'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(self.database)})
        self.apps.append(app)
        return app

    def seeded_app(self):
        app = self.make_app()
        with app.app_context():
            seed_catalog()
        return app

    def legacy_database(self):
        """Reproduce the pre-metadata schema, including existing order snapshots."""
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript('''
                CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE,
                    password VARCHAR(200) NOT NULL, is_admin BOOLEAN, created_at DATETIME);
                CREATE TABLE perfume (id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL,
                    brand VARCHAR(120), description TEXT, price FLOAT NOT NULL, stock INTEGER,
                    created_at DATETIME);
                CREATE TABLE "order" (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    checkout_token VARCHAR(96) NOT NULL UNIQUE, full_name VARCHAR(120) NOT NULL,
                    phone VARCHAR(30) NOT NULL, city VARCHAR(100) NOT NULL, address VARCHAR(500) NOT NULL,
                    note VARCHAR(1000) NOT NULL, subtotal NUMERIC(12,2) NOT NULL,
                    shipping NUMERIC(12,2) NOT NULL, total NUMERIC(12,2) NOT NULL,
                    status VARCHAR(24) NOT NULL, created_at DATETIME NOT NULL);
                CREATE TABLE order_item (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL,
                    perfume_id INTEGER NOT NULL, name VARCHAR(120) NOT NULL,
                    brand VARCHAR(120) NOT NULL, unit_price NUMERIC(12,2) NOT NULL,
                    quantity INTEGER NOT NULL, line_total NUMERIC(12,2) NOT NULL);
            ''')
            connection.execute('INSERT INTO user VALUES (1, ?, ?, 1, ?)',
                               ('existing-owner', 'preserve-existing-password', '2025-01-01 12:00:00'))
            for index, product in enumerate(load_catalog()[:5], start=1):
                connection.execute('INSERT INTO perfume VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (index, product['name'], 'Existing brand', f'Existing description {index}',
                     300.25 + index, index + 2, '2025-02-01 12:00:00'))
            connection.execute('INSERT INTO "order" VALUES (1,1,?,?,?,?,?,?,?,?,?,?,?)',
                ('existing-token', 'Original buyer', '0501234567', 'City', 'Old address',
                 'Preserve note', 123.50, 0, 123.50, 'confirmed', '2025-03-01 12:00:00'))
            connection.execute('INSERT INTO order_item VALUES (1,1,1,?,?,?,?,?)',
                               ('Historical product name', 'Historical brand', 61.75, 2, 123.50))
            connection.execute('INSERT INTO order_item VALUES (2,1,999,?,?,?,?,?)',
                               ('Deleted product snapshot', 'Historical brand', 0, 1, 0))
            connection.commit()

    def test_additive_legacy_migration_preserves_data_and_restarts_are_idempotent(self):
        self.legacy_database()
        original_records = load_catalog()[:5]
        app = self.make_app()
        for _ in range(2):
            with app.app_context():
                self.assertEqual(User.query.count(), 1)
                self.assertEqual(db.session.get(User, 1).password, 'preserve-existing-password')
                self.assertEqual(Perfume.query.count(), 5)
                for index, record in enumerate(original_records, start=1):
                    product = db.session.get(Perfume, index)
                    self.assertEqual((product.name, product.brand, product.description, product.price, product.stock),
                        (record['name'], 'Existing brand', f'Existing description {index}', 300.25 + index, index + 2))
                    self.assertEqual((product.sku, product.category, product.audience, product.volume_ml, product.image_key),
                        tuple(record[key] for key in ('sku', 'category', 'audience', 'volume_ml', 'image_key')))
                order = db.session.get(Order, 1)
                self.assertEqual((order.full_name, order.total, order.status), ('Original buyer', Decimal('123.50'), 'confirmed'))
                self.assertEqual(order.items[0].name, 'Historical product name')
                self.assertEqual(order.items[0].unit_price, Decimal('61.75'))
                self.assertEqual(order.items[0].image_key, 'rose')
                self.assertEqual(order.items[1].name, 'Deleted product snapshot')
                self.assertEqual(order.items[1].image_key, 'musk')
            app = self.make_app()
        with app.app_context():
            added = seed_catalog()
            self.assertGreaterEqual(added, 30)
            self.assertGreaterEqual(Perfume.query.count(), 35)
            self.assertEqual(seed_catalog(), 0)
            self.assertEqual(User.query.count(), 1)
            self.assertEqual(Order.query.count(), 1)
            self.assertEqual(db.session.get(Perfume, 1).price, 301.25)
            self.assertEqual(db.session.get(Perfume, 1).stock, 3)

    def test_explicit_seed_has_no_default_accounts_and_preserves_edits(self):
        app = self.make_app()
        with app.app_context():
            self.assertEqual(User.query.count(), 0)
            self.assertEqual(Perfume.query.count(), 0)
        result = app.test_cli_runner().invoke(args=['seed-catalog'])
        self.assertEqual(result.exit_code, 0, result.output)
        with app.app_context():
            count = Perfume.query.count()
            self.assertGreaterEqual(count, 35)
            self.assertEqual(User.query.count(), 0)
            self.assertEqual({p.category for p in Perfume.query.all()}, set(CATEGORIES))
            self.assertEqual({p.audience for p in Perfume.query.all()}, set(AUDIENCES))
            self.assertEqual({p.volume_ml for p in Perfume.query.all()}, set(VOLUMES))
            product = Perfume.query.order_by(Perfume.id).first()
            product.name, product.stock, product.price = 'Edited product', 1, 777.25
            db.session.commit()
            self.assertEqual(seed_catalog(), 0)
            self.assertEqual((product.name, product.stock, product.price), ('Edited product', 1, 777.25))
        restarted = self.make_app()
        self.assertEqual(restarted.test_cli_runner().invoke(args=['seed-catalog']).exit_code, 0)
        with restarted.app_context():
            self.assertEqual(Perfume.query.count(), count)
            self.assertEqual(User.query.count(), 0)

    def catalog_result(self, app, parameters):
        captured = {}
        def capture(template, **context):
            captured.update(context)
            if 'page_url' in context:
                captured['next_url'] = context['page_url'](2)
            return 'rendered:' + template
        with patch('app.render_template', side_effect=capture):
            response = app.test_client().get('/perfumes', query_string=parameters)
        self.assertEqual(response.status_code, 200)
        return captured

    def test_metadata_combination_filters_price_bounds_and_pagination_urls(self):
        app = self.seeded_app()
        with app.app_context():
            product = Perfume.query.filter_by(category='floral', audience='women', volume_ml=50).first()
            selected_id = product.id
            selected_price = str(product.price)
        parameters = {'category': 'floral', 'audience': 'women', 'volume': '50',
                      'min_price': selected_price, 'max_price': selected_price, 'sort': 'price_asc'}
        result = self.catalog_result(app, parameters)
        self.assertEqual([p.id for p in result['perfumes']], [selected_id])
        self.assertEqual(parse_qs(urlsplit(result['next_url']).query),
                         {**{k: [v] for k, v in parameters.items()}, 'page': ['2']})
        first = self.catalog_result(app, {'sort': 'price_asc', 'min_price': '0', 'max_price': '1000000'})
        second = self.catalog_result(app, {'sort': 'price_asc', 'min_price': '0', 'max_price': '1000000', 'page': '2'})
        self.assertEqual(len(first['perfumes']), 12)
        self.assertEqual(len(second['perfumes']), 12)
        self.assertFalse(set(p.id for p in first['perfumes']) & set(p.id for p in second['perfumes']))
        self.assertGreaterEqual(first['pagination'].total, 35)
        self.assertLessEqual(first['perfumes'][-1].price, second['perfumes'][0].price)
        self.assertEqual(self.catalog_result(app, {'category': 'not-a-family'})['perfumes'], [])
        for parameters in ({'volume': 'bad'}, {'min_price': 'nan'}, {'max_price': 'Infinity'},
                           {'min_price': '-1'}, {'min_price': '250', 'max_price': '100'}):
            self.assertEqual(app.test_client().get('/perfumes', query_string=parameters).status_code, 400, parameters)

    def test_create_admin_explicit_strong_credentials_and_no_overwrite(self):
        app = self.make_app()
        runner = app.test_cli_runner()
        short = runner.invoke(args=['create-admin', '--username', 'new-owner', '--password', 'admin'])
        self.assertNotEqual(short.exit_code, 0)
        password = 'Local-test-password-42'
        created = runner.invoke(args=['create-admin', '--username', 'new-owner', '--password', password])
        self.assertEqual(created.exit_code, 0, created.output)
        self.assertNotIn(password, created.output)
        with app.app_context():
            user = User.query.one()
            original = user.password
            self.assertTrue(user.is_admin)
            self.assertNotEqual(original, password)
            self.assertTrue(check_password_hash(original, password))
        duplicate = runner.invoke(args=['create-admin', '--username', 'NEW-OWNER', '--password', 'Another-test-password-43'])
        self.assertNotEqual(duplicate.exit_code, 0)
        with app.app_context():
            self.assertEqual(User.query.count(), 1)
            self.assertEqual(User.query.one().password, original)

    def test_rendered_pagination_and_sort_form_preserve_all_selected_filters(self):
        app = self.make_app()
        with app.app_context():
            db.session.add_all([Perfume(name=f'Pagination rose {index}', brand='Filter brand',
                description='Test rose notes', price=190 + index, stock=3, category='floral',
                audience='women', volume_ml=50, image_key='rose') for index in range(15)])
            db.session.commit()
        parameters = {'q': 'Pagination', 'brand': 'Filter brand', 'category': 'floral',
                      'audience': 'women', 'volume': '50', 'price': '175-225',
                      'min_price': '190', 'max_price': '225', 'availability': 'available',
                      'sort': 'price_asc'}
        client = app.test_client()
        response = client.get('/perfumes', query_string=parameters)
        self.assertEqual(response.status_code, 200)
        parsed = CatalogLinks(response.get_data(as_text=True))
        self.assertEqual(parsed.cards, 12)
        page_two = [link for link in parsed.links if urlsplit(link).path == '/perfumes'
                    and parse_qs(urlsplit(link).query).get('page') == ['2']]
        self.assertTrue(page_two, 'The catalog needs an actual link to its second page.')
        expected = {**{key: [value] for key, value in parameters.items()}, 'page': ['2']}
        for link in page_two:
            self.assertEqual(parse_qs(urlsplit(link).query), expected)
        for key, value in parameters.items():
            self.assertEqual(parsed.hidden[key], value)
        second = client.get(page_two[0])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(CatalogLinks(second.get_data(as_text=True)).cards, 3)

    def test_admin_rejects_invalid_metadata_and_order_snapshots_survive_changes(self):
        app = self.seeded_app()
        with app.app_context():
            db.session.add(User(id=1, username='owner', password='unused-test-password', is_admin=True))
            product = Perfume.query.filter_by(image_key='rose', volume_ml=50).first()
            product_id = product.id
            expected = (product.image_key, product.volume_ml, product.category, product.audience)
            db.session.commit()
            initial_count = Perfume.query.count()
        client = app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, username='owner', is_admin=True,
                           cart={str(product_id): 1}, checkout_token='catalog-order-token')
        response = client.post('/checkout', data={'full_name': 'Test customer', 'phone': '0501234567',
            'city': 'Riyadh', 'address': 'Test address', 'checkout_token': 'catalog-order-token'})
        self.assertEqual(response.location, '/orders/1')
        valid = {'name': 'Test product', 'brand': 'Test brand', 'description': 'Test notes',
                 'price': '175.50', 'stock': '3', 'category': 'fresh', 'audience': 'men',
                 'volume_ml': '150', 'image_key': 'ocean'}
        for field, invalid in (('volume_ml', '0'), ('volume_ml', '999'), ('volume_ml', 'oops'),
                               ('image_key', '../../secret'), ('image_key', 'https://example.com/a.png'),
                               ('category', 'invalid'), ('audience', 'invalid')):
            with self.subTest(field=field, invalid=invalid):
                data = {**valid, field: invalid}
                self.assertEqual(client.post('/admin/perfumes/add', data=data).status_code, 200)
                self.assertEqual(client.post(f'/admin/perfumes/{product_id}/edit', data=data).status_code, 200)
                with app.app_context():
                    self.assertEqual(Perfume.query.count(), initial_count)
                    product = db.session.get(Perfume, product_id)
                    self.assertEqual((product.image_key, product.volume_ml, product.category, product.audience), expected)
        self.assertEqual(client.post(f'/admin/perfumes/{product_id}/edit', data=valid).location, '/admin')
        self.assertEqual(client.post(f'/admin/perfumes/{product_id}/delete').location, '/admin')
        with app.app_context():
            item = OrderItem.query.one()
            self.assertEqual((item.image_key, item.volume_ml, item.category, item.audience), expected)
            self.assertEqual(item.perfume_id, 0)
            self.assertEqual(item.image_filename, 'images/' + IMAGES[expected[0]][1])
        detail = client.get('/orders/1')
        self.assertEqual(detail.status_code, 200)
        self.assertIn('/static/images/' + IMAGES[expected[0]][1],
                      CatalogLinks(detail.get_data(as_text=True)).images)
        self.assertIn(f'{expected[1]} مل', detail.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
