from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime


# ─────────────────────────────────────────
# User Loader (required by Flask-Login)
# ─────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────
# User Model
# Handles both customers and admin
# ─────────────────────────────────────────
class User(db.Model, UserMixin):
    id          = db.Column(db.Integer, primary_key=True)
    username    = db.Column(db.String(50), nullable=False, unique=True)
    email       = db.Column(db.String(120), nullable=False, unique=True)
    password    = db.Column(db.String(200), nullable=False)
    is_admin    = db.Column(db.Boolean, default=False)
    orders      = db.relationship('Order', backref='customer', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'


# ─────────────────────────────────────────
# Product Model
# Represents a shoe listing
# ─────────────────────────────────────────
class Product(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    brand       = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price       = db.Column(db.Float, nullable=False)
    stock       = db.Column(db.Integer, nullable=False, default=0)
    category    = db.Column(db.String(50), nullable=False)   # Men, Women, Kids, Unisex/Sneakers
    sizes       = db.Column(db.String(200), nullable=False)  # Stored as "40,41,42,43,44"
    image_file  = db.Column(db.String(200), default='default.jpg')

    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    cart_items  = db.relationship('Cart', backref='product', lazy=True)

    def get_sizes(self):
        # Returns sizes as a list e.g. ['40', '41', '42']
        return self.sizes.split(',')

    def __repr__(self):
        return f'<Product {self.name}>'


# ─────────────────────────────────────────
# Order Model
# A completed order placed by a customer
# ─────────────────────────────────────────
class Order(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_ordered = db.Column(db.DateTime, default=datetime.utcnow)
    status       = db.Column(db.String(50), default='Pending')  # Pending, Shipped, Delivered
    items        = db.relationship('OrderItem', backref='order', lazy=True)

    def get_total(self):
        # Calculates total price of the order
        return sum(item.quantity * item.product.price for item in self.items)

    def __repr__(self):
        return f'<Order {self.id}>'


# ─────────────────────────────────────────
# OrderItem Model
# Each shoe line inside an order
# ─────────────────────────────────────────
class OrderItem(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity   = db.Column(db.Integer, nullable=False, default=1)
    size       = db.Column(db.String(10), nullable=False)  # Size customer selected

    def __repr__(self):
        return f'<OrderItem order={self.order_id} product={self.product_id}>'


# ─────────────────────────────────────────
# Cart Model
# Temporary items before checkout
# ─────────────────────────────────────────
class Cart(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity   = db.Column(db.Integer, nullable=False, default=1)
    size       = db.Column(db.String(10), nullable=False)  # Size selected for this item

    def __repr__(self):
        return f'<Cart user={self.user_id} product={self.product_id}>'