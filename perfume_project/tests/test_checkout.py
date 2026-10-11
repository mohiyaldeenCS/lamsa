"""Run with: python -m unittest discover -s tests -v.

Every test uses an isolated SQLite database; the real shop is never modified.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app
from forms import PerfumeForm, RegisterForm
from models import Order, OrderItem, Perfume, User, db


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret',
            'WTF_CSRF_ENABLED': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(Path(self.directory.name) / 'test.db')})
        self.client = self.app.test_client()
        self.render = patch('app.render_template', side_effect=lambda template, **kwargs: 'rendered:' + template)
        self.render_mock = self.render.start()
        with self.app.app_context():
            db.session.add_all([
                User(id=1, username='customer', password=generate_password_hash('password')),
                User(id=2, username='other', password=generate_password_hash('password')),
                User(id=3, username='admin', password=generate_password_hash('password'), is_admin=True),
                Perfume(id=1, name='ورد', brand='لمسة', description='ورد مسك', price=189.25, stock=3),
                Perfume(id=2, name='عود', brand='لمسة', description='عود عنبر', price=245, stock=1),
                Perfume(id=3, name='فانيلا', brand='لمسة', description='فانيلا', price=200, stock=0),
            ])
            db.session.commit()

    def tearDown(self):
        self.render.stop()
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def auth(self, client=None, uid=1, cart=None, token='checkout-unique-token'):
        client = client or self.client
        with client.session_transaction() as session:
            session['user_id'] = uid
            session['username'] = 'admin' if uid == 3 else 'customer'
            session['is_admin'] = uid == 3
            session['checkout_token'] = token
            if cart is not None:
                session['cart'] = cart
        return token

    def checkout(self, client=None, token='checkout-unique-token', **overrides):
        payload = {'full_name': 'محمد أحمد', 'phone': '0501234567', 'city': 'الرياض',
                   'address': 'حي النرجس، شارع الزهور', 'note': '', 'checkout_token': token}
        payload.update(overrides)
        return (client or self.client).post('/checkout', data=payload)

    def test_order_snapshot_decimal_total_duplicate_and_empty_cart(self):
        self.auth(cart={'1': 2, '2': 1})
        response = self.checkout()
        self.assertEqual(response.location, '/orders/1')
        self.assertEqual(self.checkout().location, '/orders/1')
        with self.app.app_context():
            order = db.session.get(Order, 1)
            self.assertEqual(Order.query.count(), 1)
            self.assertEqual(order.total, Decimal('623.50'))
            self.assertEqual(len(order.items), 2)
            self.assertEqual(db.session.get(Perfume, 1).stock, 1)
            self.assertEqual(db.session.get(Perfume, 2).stock, 0)
            db.session.delete(db.session.get(Perfume, 1))
            db.session.commit()
            self.assertEqual(db.session.get(Order, 1).items[0].name, 'ورد')
        with self.client.session_transaction() as session:
            self.assertNotIn('cart', session)

    def test_checkout_ownership_and_admin_permission(self):
        self.assertIn('/login', self.client.get('/checkout').location)
        self.auth(cart={'1': 1})
        self.checkout()
        self.assertEqual(self.client.get('/orders/1').status_code, 200)
        self.auth(uid=2)
        self.assertEqual(self.client.get('/orders/1').status_code, 404)
        self.assertIn('/login', self.client.get('/admin/orders').location)
        self.assertIn('/login', self.client.post('/admin/orders/1/status', data={'status': 'cancelled'}).location)
        self.auth(uid=3)
        self.assertEqual(self.client.get('/orders/1').status_code, 200)
        self.assertEqual(self.client.get('/admin/orders').status_code, 200)

    def test_stock_changes_do_not_create_partial_order(self):
        self.auth(cart={'1': 2, '2': 2})
        self.assertEqual(self.checkout().location, '/cart')
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(db.session.get(Perfume, 1).stock, 3)
        self.client.get('/cart')
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'], {'1': 2, '2': 1})

    def test_cancel_restores_stock_once_and_terminal_status_cannot_reopen(self):
        self.auth(cart={'1': 2})
        self.checkout()
        self.auth(uid=3)
        for _ in range(2):
            self.client.post('/admin/orders/1/status', data={'status': 'cancelled'})
        self.client.post('/admin/orders/1/status', data={'status': 'confirmed'})
        with self.app.app_context():
            self.assertEqual(db.session.get(Perfume, 1).stock, 3)
            self.assertEqual(db.session.get(Order, 1).status, 'cancelled')

    def test_order_progression_and_invalid_status(self):
        self.auth(cart={'1': 1})
        self.checkout()
        self.auth(uid=3)
        self.assertEqual(self.client.post('/admin/orders/1/status', data={'status': 'unknown'}).status_code, 400)
        for status in ('confirmed', 'preparing', 'completed', 'cancelled'):
            self.client.post('/admin/orders/1/status', data={'status': status})
        with self.app.app_context():
            self.assertEqual(db.session.get(Order, 1).status, 'completed')
            self.assertEqual(db.session.get(Perfume, 1).stock, 2)

    def test_invalid_details_and_forged_token_never_create_order(self):
        self.auth(cart={'1': 1})
        self.assertEqual(self.checkout(phone='not-a-phone').status_code, 200)
        self.assertEqual(self.checkout(token='not-the-issued-token').location, '/checkout')
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)

    def test_concurrent_buyers_cannot_both_purchase_last_item(self):
        first, second = self.app.test_client(), self.app.test_client()
        self.auth(first, uid=1, cart={'2': 1}, token='first-token')
        self.auth(second, uid=2, cart={'2': 1}, token='second-token')
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.checkout, first, 'first-token'),
                       executor.submit(self.checkout, second, 'second-token')]
            responses = [future.result() for future in futures]
        self.assertTrue(all(response.status_code == 302 for response in responses))
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 1)
            self.assertEqual(db.session.get(Perfume, 2).stock, 0)

    def test_csrf_and_post_only_mutations(self):
        self.auth(cart={'1': 1})
        self.app.config['WTF_CSRF_ENABLED'] = True
        for route in ('/cart/add/1', '/cart/remove/1', '/cart/clear', '/cart/update', '/wishlist/1', '/checkout', '/logout'):
            self.assertEqual(self.client.post(route).status_code, 400, route)
        for route in ('/cart/add/1', '/cart/clear', '/wishlist/1', '/logout'):
            self.assertEqual(self.client.get(route).status_code, 405, route)

    def test_cart_sanitizes_invalid_and_sold_out_quantities(self):
        self.auth(cart={'invalid': 'word', '1': -5, '2': 99, '3': 4, '99': 1})
        self.assertEqual(self.client.get('/cart').status_code, 200)
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'], {'2': 1})
        with self.app.app_context():
            db.session.get(Perfume, 2).stock = 0
            db.session.commit()
        self.client.post('/cart/update')
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'], {})

    def test_local_redirects_and_zero_stock_form(self):
        for target in ('//evil.test', 'https://evil.test/', '/\\evil.test', 'http://['):
            response = self.client.post('/login', query_string={'next': target}, data={'username': 'customer', 'password': 'password'})
            self.assertEqual(response.location, '/profile')
        self.assertEqual(self.client.post('/cart/add/1', headers={'Referer': 'https://evil.test'}).location, '/cart')
        with self.app.test_request_context(method='POST', data={'name': 'test', 'brand': 'test', 'description': 'test', 'price': '0', 'stock': '0'}):
            self.assertTrue(PerfumeForm().validate())

    def test_wishlist_and_recommendations_use_existing_available_inventory(self):
        self.client.post('/wishlist/1')
        self.client.get('/wishlist')
        self.assertEqual([p.id for p in self.render_mock.call_args.kwargs['perfumes']], [1])
        response = self.client.post('/fragrance-finder', data={'family': 'woody', 'occasion': 'evening', 'intensity': 'bold'})
        self.assertEqual(response.status_code, 200)
        recommended = self.render_mock.call_args.kwargs['recommendations']
        self.assertEqual(recommended[0].id, 2)
        self.assertNotIn(3, [p.id for p in recommended])
        self.assertTrue(self.render_mock.call_args.kwargs['submitted'])

    def test_transaction_rolls_back_earlier_stock_update_when_later_update_fails(self):
        self.auth(cart={'1': 1, '2': 1})
        original_execute = db.session.execute
        stock_updates = 0

        def lose_second_stock_update(statement, *args, **kwargs):
            nonlocal stock_updates
            if str(statement).startswith('UPDATE perfume '):
                stock_updates += 1
                if stock_updates == 2:
                    return SimpleNamespace(rowcount=0)
            return original_execute(statement, *args, **kwargs)

        with patch.object(db.session, 'execute', side_effect=lose_second_stock_update):
            self.assertEqual(self.checkout().location, '/cart')
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(OrderItem.query.count(), 0)
            self.assertEqual(db.session.get(Perfume, 1).stock, 3)
            self.assertEqual(db.session.get(Perfume, 2).stock, 1)

    def test_concurrent_cancellations_restore_stock_only_once(self):
        self.auth(cart={'1': 2})
        self.checkout()
        first, second = self.app.test_client(), self.app.test_client()
        self.auth(first, uid=3)
        self.auth(second, uid=3)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(client.post, '/admin/orders/1/status', data={'status': 'cancelled'})
                       for client in (first, second)]
            self.assertTrue(all(future.result().status_code == 302 for future in futures))
        with self.app.app_context():
            self.assertEqual(db.session.get(Perfume, 1).stock, 3)
            self.assertEqual(db.session.get(Order, 1).status, 'cancelled')

    def test_deleting_product_does_not_restock_reused_id(self):
        self.auth(cart={'2': 1})
        self.checkout()
        self.auth(uid=3)
        self.client.post('/admin/perfumes/2/delete')
        with self.app.app_context():
            db.session.add(Perfume(id=2, name='Replacement', price=300, stock=5))
            db.session.commit()
        self.client.post('/admin/orders/1/status', data={'status': 'cancelled'})
        with self.app.app_context():
            self.assertEqual(db.session.get(Perfume, 2).stock, 5)
            self.assertEqual(db.session.get(Order, 1).items[0].name, 'عود')

    def test_legacy_password_migrates_but_hash_is_not_a_password(self):
        encoded = generate_password_hash('legacy-password', method='pbkdf2:sha256:1000')
        with self.app.app_context():
            db.session.get(User, 1).password = encoded
            db.session.get(User, 2).password = 'legacy-password'
            db.session.commit()
        self.assertEqual(self.client.post('/login', data={'username': 'customer', 'password': encoded}).status_code, 200)
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)
        self.assertEqual(self.client.post('/login', data={'username': 'other', 'password': 'legacy-password'}).location, '/profile')
        with self.app.app_context():
            self.assertNotEqual(db.session.get(User, 2).password, 'legacy-password')

    def test_form_trimming_limits_nonfinite_prices_and_money_display(self):
        with self.app.test_request_context(method='POST', data={'username': ' a ', 'password': 'password', 'password2': 'password'}):
            self.assertFalse(RegisterForm().validate())
        for value in ('nan', 'inf', '-inf'):
            with self.app.test_request_context(method='POST', data={'name': 'test', 'brand': 'test', 'description': 'test', 'price': value, 'stock': '1'}):
                self.assertFalse(PerfumeForm().validate())
        self.auth(cart={'1': 1})
        self.assertEqual(self.checkout(full_name=' a ').status_code, 200)
        self.assertEqual(self.checkout(phone='0------').status_code, 200)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(self.app.jinja_env.filters['sar'](189.25), '189.25 ر.س')
            self.assertEqual(self.app.jinja_env.filters['sar'](245), '245 ر.س')

    def test_valid_csrf_checkout_and_admin_protection(self):
        from flask_wtf.csrf import generate_csrf
        self.auth(cart={'1': 1})
        self.app.config['WTF_CSRF_ENABLED'] = True
        with self.app.test_request_context():
            csrf_token = generate_csrf()
            from flask import session
            raw_token = session['csrf_token']
        with self.client.session_transaction() as session:
            session['csrf_token'] = raw_token
        self.assertEqual(self.checkout(csrf_token=csrf_token).location, '/orders/1')
        self.auth(uid=3)
        self.assertEqual(self.client.post('/admin/orders/1/status', data={'status': 'cancelled'}).status_code, 400)
        self.assertEqual(self.client.post('/admin/perfumes/1/delete').status_code, 400)


if __name__ == '__main__':
    unittest.main()
