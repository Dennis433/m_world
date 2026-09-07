from flask import Blueprint, render_template, request
from app.models import Product

shop = Blueprint('shop', __name__)


@shop.route('/')
def home():
    category = request.args.get('category')
    if category:
        products = Product.query.filter_by(category=category).all()
    else:
        products = Product.query.all()
    return render_template('shop/home.html', products=products)


@shop.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('shop/product_detail.html', product=product)