from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from uuid import uuid4

from catalog import AUDIENCES, CATEGORIES, image_filename

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'

class Perfume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    brand = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False, default=0.0)
    stock = db.Column(db.Integer, default=10)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sku = db.Column(db.String(40), nullable=False, unique=True, default=lambda: 'LM-' + uuid4().hex[:16].upper())
    category = db.Column(db.String(24), nullable=False, default='woody', index=True)
    audience = db.Column(db.String(16), nullable=False, default='unisex', index=True)
    volume_ml = db.Column(db.Integer, nullable=False, default=100)
    image_key = db.Column(db.String(24), nullable=False, default='musk')
    featured = db.Column(db.Boolean, nullable=False, default=False)

    @property
    def category_label(self):
        return CATEGORIES.get(self.category, CATEGORIES['woody'])

    @property
    def audience_label(self):
        return AUDIENCES.get(self.audience, AUDIENCES['unisex'])

    @property
    def image_filename(self):
        return image_filename(self.image_key)

    def __repr__(self):
        return f'<Perfume {self.name}>'


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    checkout_token = db.Column(db.String(96), nullable=False, unique=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(500), nullable=False)
    note = db.Column(db.String(1000), nullable=False, default='')
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    shipping = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(24), nullable=False, default='pending', index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy='selectin', cascade='all, delete-orphan')

    @property
    def number(self):
        return f'LM-{self.id:05d}'


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False, index=True)
    # Deliberately retain snapshots even when an administrator deletes a product.
    perfume_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    brand = db.Column(db.String(120), nullable=False, default='')
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    image_key = db.Column(db.String(24), nullable=False, default='musk')
    volume_ml = db.Column(db.Integer, nullable=False, default=100)
    category = db.Column(db.String(24), nullable=False, default='woody')
    audience = db.Column(db.String(16), nullable=False, default='unisex')

    @property
    def image_filename(self):
        return image_filename(self.image_key)

    @property
    def category_label(self):
        return CATEGORIES.get(self.category, CATEGORIES['woody'])

    @property
    def audience_label(self):
        return AUDIENCES.get(self.audience, AUDIENCES['unisex'])
