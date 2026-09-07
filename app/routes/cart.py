from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Cart, Product, Order, OrderItem
import requests
import hmac
import hashlib
import json

cart = Blueprint('cart', __name__)


# ─────────────────────────────────────────
# View Cart
# ─────────────────────────────────────────
@cart.route('/cart')
@login_required
def view_cart():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('cart/cart.html', cart_items=cart_items, total=total)


# ─────────────────────────────────────────
# Add to Cart
# ─────────────────────────────────────────
@cart.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product  = Product.query.get_or_404(product_id)
    size     = request.form.get('size')
    quantity = int(request.form.get('quantity', 1))

    if not size:
        flash('Please select a size.', 'warning')
        return redirect(url_for('shop.product_detail', product_id=product_id))

    existing = Cart.query.filter_by(
        user_id=current_user.id,
        product_id=product_id,
        size=size
    ).first()

    if existing:
        existing.quantity += quantity
    else:
        cart_item = Cart(
            user_id=current_user.id,
            product_id=product_id,
            quantity=quantity,
            size=size
        )
        db.session.add(cart_item)

    db.session.commit()

    # "Buy Now" → go straight to checkout
    if request.args.get('buy_now') == '1':
        return redirect(url_for('cart.checkout'))

    flash(f'{product.name} (Size {size}) added to cart!', 'success')
    return redirect(url_for('cart.view_cart'))


# ─────────────────────────────────────────
# Remove from Cart
# ─────────────────────────────────────────
@cart.route('/cart/remove/<int:cart_id>')
@login_required
def remove_from_cart(cart_id):
    item = Cart.query.get_or_404(cart_id)
    if item.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('cart.view_cart'))
    db.session.delete(item)
    db.session.commit()
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart.view_cart'))


# ─────────────────────────────────────────
# Checkout Page
# ─────────────────────────────────────────
@cart.route('/checkout')
@login_required
def checkout():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('cart.view_cart'))
    total = sum(item.product.price * item.quantity for item in cart_items)
    flw_public_key = current_app.config.get('FLW_PUBLIC_KEY', '')
    return render_template('cart/checkout.html',
                           cart_items=cart_items,
                           total=total,
                           flw_public_key=flw_public_key)


# ─────────────────────────────────────────
# Initiate Flutterwave Payment
# ─────────────────────────────────────────
@cart.route('/payment/initiate', methods=['POST'])
@login_required
def initiate_payment():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        return jsonify({'error': 'Cart is empty'}), 400

    total_naira = sum(item.product.price * item.quantity for item in cart_items)
    secret_key  = current_app.config.get('FLW_SECRET_KEY', '')

    import uuid
    tx_ref = f"MWORLD-{current_user.id}-{uuid.uuid4().hex[:10].upper()}"

    headers = {
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'tx_ref':       tx_ref,
        'amount':       str(total_naira),
        'currency':     'NGN',
        'redirect_url': url_for('cart.payment_callback', _external=True),
        'customer': {
            'email':    current_user.email,
            'name':     current_user.username,
        },
        'customizations': {
            'title':       'M World Luxury',
            'description': 'Premium Footwear Payment',
            'logo':        url_for('static', filename='images/default.jpg', _external=True),
        },
        'meta': {
            'user_id': current_user.id,
            'tx_ref':  tx_ref,
        }
    }

    try:
        res  = requests.post('https://api.flutterwave.com/v3/payments',
                             headers=headers, json=payload, timeout=15)
        data = res.json()
        if data.get('status') == 'success':
            return jsonify({'payment_link': data['data']['link'], 'tx_ref': tx_ref})
        else:
            return jsonify({'error': data.get('message', 'Payment init failed')}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# Payment Callback (Flutterwave redirects here)
# ─────────────────────────────────────────
@cart.route('/payment/callback')
@login_required
def payment_callback():
    status      = request.args.get('status')
    tx_ref      = request.args.get('tx_ref')
    transaction_id = request.args.get('transaction_id')

    if status != 'successful' or not transaction_id:
        flash('❌ Payment was not successful. Please try again.', 'danger')
        return redirect(url_for('cart.checkout'))

    # Verify with Flutterwave
    secret_key = current_app.config.get('FLW_SECRET_KEY', '')
    headers    = {'Authorization': f'Bearer {secret_key}'}

    try:
        res  = requests.get(f'https://api.flutterwave.com/v3/transactions/{transaction_id}/verify',
                            headers=headers, timeout=15)
        data = res.json()

        txn = data.get('data', {})
        if (data.get('status') == 'success'
                and txn.get('status') == 'successful'
                and txn.get('currency') == 'NGN'):

            cart_items = Cart.query.filter_by(user_id=current_user.id).all()
            if not cart_items:
                flash('Cart already processed.', 'info')
                return redirect(url_for('shop.home'))

            order = Order(user_id=current_user.id, status='Paid', payment_ref=tx_ref)
            db.session.add(order)
            db.session.flush()

            for item in cart_items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    size=item.size,
                    price_each=item.product.price
                )
                item.product.stock -= item.quantity
                db.session.add(order_item)
                db.session.delete(item)

            db.session.commit()
            flash(f'🎉 Payment successful! Order #{order.id} confirmed.', 'success')
            return redirect(url_for('cart.order_success', order_id=order.id))
        else:
            flash('❌ Payment verification failed. Contact support if charged.', 'danger')
            return redirect(url_for('cart.checkout'))

    except Exception as e:
        flash(f'Verification error: {str(e)}', 'danger')
        return redirect(url_for('cart.checkout'))


# ─────────────────────────────────────────
# Flutterwave Webhook (backup verification)
# ─────────────────────────────────────────
@cart.route('/payment/webhook', methods=['POST'])
def flutterwave_webhook():
    secret_hash = current_app.config.get('FLW_SECRET_HASH', '')
    signature   = request.headers.get('verif-hash', '')

    if signature != secret_hash:
        return jsonify({'error': 'Invalid signature'}), 400

    event = request.get_json()
    if event.get('event') == 'charge.completed' and event['data']['status'] == 'successful':
        # Backup safety net — main logic handled in callback
        pass

    return jsonify({'status': 'ok'}), 200


# ─────────────────────────────────────────
# Order Success Page
# ─────────────────────────────────────────
@cart.route('/order/success/<int:order_id>')
@login_required
def order_success(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('shop.home'))
    return render_template('cart/order_success.html', order=order)