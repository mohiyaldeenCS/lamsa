"""Exercise actual Jinja pages and CSRF-protected flows against a temporary DB."""
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from app import create_app
from models import Order, Perfume, User, db


class HiddenFields(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == 'input' and fields.get('type') == 'hidden' and fields.get('name'):
            self.values[fields['name']] = fields.get('value', '')


class TemplateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'isolated-render-test',
            'WTF_CSRF_ENABLED': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(Path(self.directory.name) / 'render.db')})
        self.client = self.app.test_client()
        with self.app.app_context():
            db.session.add(User(username='render-admin',
                password=generate_password_hash('admin-password'), is_admin=True))
            db.session.add_all([
                Perfume(id=1, name='ورد الاختبار', brand='لمسة', description='ورد، مسك', price=189.25, stock=5),
                Perfume(id=2, name='بحر الاختبار', brand='أمواج', description='بحر، برغموت', price=165, stock=3),
                Perfume(id=3, name='مسك الاختبار', brand='لمسة', description='عود، مسك', price=245, stock=0),
            ])
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def page(self, path, status=200):
        response = self.client.get(path)
        self.assertEqual(response.status_code, status, path)
        self.assertIn('<html lang="ar" dir="rtl">', response.get_data(as_text=True), path)
        return response

    def submit(self, source, target, data=None):
        fields = HiddenFields(self.page(source).get_data(as_text=True)).values
        self.assertIn('csrf_token', fields, source)
        fields.update(data or {})
        return self.client.post(target, data=fields)

    def test_real_templates_and_complete_customer_admin_flow(self):
        for path in ('/', '/about', '/register', '/login', '/perfumes',
                     '/perfumes?q=ورد&sort=price_asc', '/perfumes?brand=لمسة&availability=available',
                     '/perfumes?q=definitely-no-results', '/perfumes/1', '/perfumes/3',
                     '/cart', '/wishlist', '/fragrance-finder'):
            self.page(path)
        self.page('/missing-page', 404)
        self.page('/perfumes/99999', 404)
        for path in ('/profile', '/checkout', '/admin', '/admin/orders'):
            self.assertEqual(self.client.get(path).status_code, 302, path)

        self.assertEqual(self.submit('/register', '/register', {
            'username': 'render-customer', 'password': 'customer-password',
            'password2': 'customer-password'}).location, '/login')
        invalid = self.submit('/login', '/login', {'username': 'render-customer', 'password': 'wrong'})
        self.assertEqual(invalid.status_code, 200)
        self.assertIn('غير صحيحة', invalid.get_data(as_text=True))
        self.assertEqual(self.submit('/login', '/login', {
            'username': 'render-customer', 'password': 'customer-password'}).location, '/profile')
        self.page('/profile')
        self.assertEqual(self.submit('/perfumes/1', '/wishlist/1').status_code, 302)
        self.assertIn('ورد الاختبار', self.page('/wishlist').get_data(as_text=True))
        finder = self.submit('/fragrance-finder', '/fragrance-finder', {
            'family': 'floral', 'occasion': 'everyday', 'intensity': 'soft'})
        self.assertEqual(finder.status_code, 200)
        self.assertIn('ورد الاختبار', finder.get_data(as_text=True))

        self.assertEqual(self.submit('/perfumes/1', '/cart/add/1', {'quantity': '2'}).status_code, 302)
        self.assertIn('378.50', self.page('/cart').get_data(as_text=True))
        checkout = self.page('/checkout').get_data(as_text=True)
        fields = HiddenFields(checkout).values
        fields.update(full_name='عميل الاختبار', phone='0501234567', city='الرياض',
                      address='شارع الاختبار، حي الاختبار', note='اختبار محلي')
        response = self.client.post('/checkout', data=fields)
        self.assertEqual(response.location, '/orders/1')
        self.assertEqual(self.client.post('/checkout', data=fields).location, '/orders/1')
        order_page = self.page('/orders/1').get_data(as_text=True)
        self.assertIn('LM-00001', order_page)
        self.assertIn('378.50', order_page)
        self.assertIn('عميل الاختبار', order_page)
        self.assertIn('LM-00001', self.page('/profile').get_data(as_text=True))
        self.assertEqual(self.submit('/profile', '/logout').location, '/')

        self.assertEqual(self.submit('/login', '/login', {
            'username': 'render-admin', 'password': 'admin-password'}).location, '/profile')
        for path in ('/profile', '/admin', '/admin/orders', '/orders/1',
                     '/admin/perfumes/add', '/add_perfume', '/admin/perfumes/1/edit'):
            self.page(path)
        self.assertEqual(self.submit('/admin/perfumes/add', '/admin/perfumes/add', {
            'name': 'عطر جديد', 'brand': 'دار الاختبار', 'description': 'عنبر، ورد',
            'price': '200.50', 'stock': '4'}).location, '/admin')
        with self.app.app_context():
            product_id = Perfume.query.filter_by(name='عطر جديد').one().id
        self.page(f'/perfumes/{product_id}')
        self.assertEqual(self.submit(f'/admin/perfumes/{product_id}/edit',
            f'/admin/perfumes/{product_id}/edit', {'name': 'عطر معدل', 'brand': 'دار الاختبار',
            'description': 'عنبر، ورد، مسك', 'price': '201.75', 'stock': '5'}).location, '/admin')
        self.assertEqual(self.submit('/admin', f'/admin/perfumes/{product_id}/delete').location, '/admin')
        self.page(f'/perfumes/{product_id}', 404)
        self.assertEqual(self.submit('/admin/orders', '/admin/orders/1/status',
            {'status': 'confirmed'}).location, '/admin/orders')
        self.assertEqual(self.submit('/admin/orders', '/admin/orders/1/status',
            {'status': 'cancelled'}).location, '/admin/orders')
        self.assertIn('ملغي', self.page('/orders/1').get_data(as_text=True))
        self.assertIn('حالة نهائية', self.page('/admin/orders').get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 1)
            self.assertEqual(db.session.get(Order, 1).total, Decimal('378.50'))
            self.assertEqual(db.session.get(Perfume, 1).stock, 5)


if __name__ == '__main__':
    unittest.main()
