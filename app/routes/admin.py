from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from app import db
from app.models import User, Product, Order, Cart
import os
from werkzeug.utils import secure_filename
from flask import current_app
from PIL import Image, ImageEnhance, ImageFilter

admin = Blueprint('admin', __name__)


# ─────────────────────────────────────────
# Admin required decorator
# ─────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access only.', 'danger')
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ─────────────────────────────────────────
# Image processing helper
# ─────────────────────────────────────────
def process_image(image_file, filename):
    upload_folder = current_app.config['UPLOAD_FOLDER']
    filename = os.path.splitext(filename)[0] + '.jpg'
    filepath = os.path.join(upload_folder, filename)
    img = Image.open(image_file)
    if img.mode in ('RGBA', 'P', 'LA'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background
    else:
        img = img.convert('RGB')
    width, height = img.size
    min_dim = min(width, height)
    left   = (width - min_dim) // 2
    top    = (height - min_dim) // 2
    img    = img.crop((left, top, left + min_dim, top + min_dim))
    img = img.resize((600, 600), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.4)
    img.save(filepath, 'JPEG', quality=97, optimize=True)
    return filename


# ─────────────────────────────────────────
# TEMPORARY: Setup Admin Route
# DELETE THIS AFTER FIRST USE
# ─────────────────────────────────────────
@admin.route('/setup-admin')
def setup_admin():
    existing = User.query.filter_by(email='eriggap16@gmail.com').first()
    if existing:
        existing.password = generate_password_hash('DENNIS234')
        existing.is_admin = True
        db.session.commit()
        return 'Admin updated! Now delete this route.'
    else:
        new_admin = User(
            username='MOSCOWW',
            email='eriggap16@gmail.com',
            password=generate_password_hash('DENNIS234'),
            is_admin=True
        )
        db.session.add(new_admin)
        db.session.commit()
        return 'Admin created! Now delete this route.'


# ─────────────────────────────────────────
# Admin Login
# ─────────────────────────────────────────
@admin.route('/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')
        user     = User.query.filter_by(email=email, is_admin=True).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')
    return render_template('admin/admin_login.html')


# ─────────────────────────────────────────
# Admin Logout
# ─────────────────────────────────────────
@admin.route('/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin.admin_login'))


# ─────────────────────────────────────────
# Admin Dashboard
# ─────────────────────────────────────────
@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_products = Product.query.count()
    total_orders   = Order.query.count()
    total_users    = User.query.filter_by(is_admin=False).count()
    recent_orders  = Order.query.order_by(Order.date_ordered.desc()).limit(5).all()
    return render_template('admin/dashboard.html',
        total_products=total_products,
        total_orders=total_orders,
        total_users=total_users,
        recent_orders=recent_orders
    )


# ─────────────────────────────────────────
# View All Products
# ─────────────────────────────────────────
@admin.route('/products')
@login_required
@admin_required
def products():
    all_products = Product.query.all()
    return render_template('admin/products.html', products=all_products)


# ─────────────────────────────────────────
# Add Product
# ─────────────────────────────────────────
@admin.route('/products/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    if request.method == 'POST':
        name        = request.form.get('name')
        brand       = request.form.get('brand')
        description = request.form.get('description')
        price       = request.form.get('price')
        stock       = request.form.get('stock')
        category    = request.form.get('category')
        sizes       = request.form.get('sizes')
        image       = request.files.get('image')
        image_filename = 'default.jpg'
        if image and image.filename != '':
            ext            = os.path.splitext(secure_filename(image.filename))[1]
            filename       = secure_filename(name.replace(' ', '_') + ext)
            image_filename = process_image(image, filename)
        product = Product(
            name=name,
            brand=brand,
            description=description,
            price=float(price),
            stock=int(stock),
            category=category,
            sizes=sizes,
            image_file=image_filename
        )
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin.products'))
    return render_template('admin/add_product.html')


# ─────────────────────────────────────────
# Edit Product
# ─────────────────────────────────────────
@admin.route('/products/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name        = request.form.get('name')
        product.brand       = request.form.get('brand')
        product.description = request.form.get('description')
        product.price       = float(request.form.get('price'))
        product.stock       = int(request.form.get('stock'))
        product.category    = request.form.get('category')
        product.sizes       = request.form.get('sizes')
        image = request.files.get('image')
        if image and image.filename != '':
            ext                = os.path.splitext(secure_filename(image.filename))[1]
            filename           = secure_filename(product.name.replace(' ', '_') + ext)
            product.image_file = process_image(image, filename)
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin.products'))
    return render_template('admin/edit_product.html', product=product)


# ─────────────────────────────────────────
# Delete Product
# ─────────────────────────────────────────
@admin.route('/products/delete/<int:product_id>')
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted.', 'info')
    return redirect(url_for('admin.products'))


# ─────────────────────────────────────────
# View All Orders
# ─────────────────────────────────────────
@admin.route('/orders')
@login_required
@admin_required
def orders():
    all_orders = Order.query.order_by(Order.date_ordered.desc()).all()
    return render_template('admin/orders.html', orders=all_orders)


# ─────────────────────────────────────────
# Update Order Status
# ─────────────────────────────────────────
@admin.route('/orders/update/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_order(order_id):
    order        = Order.query.get_or_404(order_id)
    order.status = request.form.get('status')
    db.session.commit()
    flash('Order status updated.', 'success')
    return redirect(url_for('admin.orders'))
