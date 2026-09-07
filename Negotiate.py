from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, current_app)
from flask_login import login_required, current_user
from app import db
from app.models import Negotiation, Product, Order, OrderItem
import requests
import uuid

negotiate = Blueprint('negotiate', __name__)


# ─────────────────────────────────────────
# Helper: build a WhatsApp click-to-chat link
# ─────────────────────────────────────────
def whatsapp_link(number, text):
    from urllib.parse import quote
    return f"https://wa.me/{number}?text={quote(text)}"


# ─────────────────────────────────────────
# User: submit a price offer (from product page)
# ─────────────────────────────────────────
@negotiate.route('/negotiate/<int:product_id>', methods=['POST'])
@login_required
def make_offer(product_id):
    product  = Product.query.get_or_404(product_id)
    size     = request.form.get('size')
    quantity = int(request.form.get('quantity', 1))
    offer    = request.form.get('offer_price')
    message  = request.form.get('message', '').strip()

    if not size:
        flash('Please select a size before negotiating.', 'warning')
        return redirect(url_for('shop.product_detail', product_id=product_id))

    try:
        offer_price = float(offer)
        if offer_price <= 0:
            raise ValueError
    except (TypeError, ValueError):
        flash('Please enter a valid offer price.', 'warning')
        return redirect(url_for('shop.product_detail', product_id=product_id))

    nego = Negotiation(
        user_id=current_user.id,
        product_id=product_id,
        size=size,
        quantity=quantity,
        offer_price=offer_price,
        user_message=message,
        status='pending'
    )
    db.session.add(nego)
    db.session.commit()

    flash('💬 Your offer has been sent to the seller! Track it under "My Offers".', 'success')
    return redirect(url_for('negotiate.my_offers'))


# ─────────────────────────────────────────
# User: view all my negotiations
# ─────────────────────────────────────────
@negotiate.route('/my-offers')
@login_required
def my_offers():
    offers = (Negotiation.query
              .filter_by(user_id=current_user.id)
              .order_by(Negotiation.updated_at.desc())
              .all())

    admin_wa = current_app.config.get('ADMIN_WHATSAPP', '')
    wa_links = {}
    for o in offers:
        text = (f"Hi M World Luxury! I'm negotiating on '{o.product.name}' "
                f"(Size {o.size}, Qty {o.quantity}). My offer: ₦{o.offer_price:,.0f} each. "
                f"[Offer #{o.id}]")
        wa_links[o.id] = whatsapp_link(admin_wa, text)

    return render_template('negotiate/my_offers.html', offers=offers, wa_links=wa_links)


# ─────────────────────────────────────────
# User: accept admin's counter price
# ─────────────────────────────────────────
@negotiate.route('/my-offers/accept/<int:nego_id>', methods=['POST'])
@login_required
def accept_counter(nego_id):
    nego = Negotiation.query.get_or_404(nego_id)
    if nego.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('negotiate.my_offers'))

    if nego.status != 'countered':
        flash('This offer is not awaiting your response.', 'info')
        return redirect(url_for('negotiate.my_offers'))

    nego.agreed_price = nego.admin_price
    nego.status = 'accepted'
    db.session.commit()
    flash('✅ Deal accepted! You can now proceed to payment.', 'success')
    return redirect(url_for('negotiate.my_offers'))


# ─────────────────────────────────────────
# User: cancel/withdraw an offer
# ─────────────────────────────────────────
@negotiate.route('/my-offers/cancel/<int:nego_id>', methods=['POST'])
@login_required
def cancel_offer(nego_id):
    nego = Negotiation.query.get_or_404(nego_id)
    if nego.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('negotiate.my_offers'))
    if nego.status in ('paid',):
        flash('Paid offers cannot be cancelled.', 'warning')
        return redirect(url_for('negotiate.my_offers'))
    db.session.delete(nego)
    db.session.commit()
    flash('Offer withdrawn.', 'info')
    return redirect(url_for('negotiate.my_offers'))


# ─────────────────────────────────────────
# User: checkout page for an accepted negotiation
# ─────────────────────────────────────────
@negotiate.route('/negotiate/checkout/<int:nego_id>')
@login_required
def nego_checkout(nego_id):
    nego = Negotiation.query.get_or_404(nego_id)
    if nego.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('negotiate.my_offers'))
    if nego.status != 'accepted':
        flash('This offer is not ready for payment yet.', 'warning')
        return redirect(url_for('negotiate.my_offers'))

    return render_template('negotiate/nego_checkout.html', nego=nego)


# ─────────────────────────────────────────
# User: initiate Flutterwave payment for a negotiation
# ─────────────────────────────────────────
@negotiate.route('/negotiate/payment/<int:nego_id>', methods=['POST'])
@login_required
def nego_payment(nego_id):
    nego = Negotiation.query.get_or_404(nego_id)
    if nego.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    if nego.status != 'accepted':
        return jsonify({'error': 'This offer is not ready for payment.'}), 400

    amount     = nego.total_amount()
    secret_key = current_app.config.get('FLW_SECRET_KEY', '')
    tx_ref     = f"MWORLD-NEGO-{nego.id}-{uuid.uuid4().hex[:8].upper()}"

    headers = {'Authorization': f'Bearer {secret_key}', 'Content-Type': 'application/json'}
    payload = {
        'tx_ref':       tx_ref,
        'amount':       str(amount),
        'currency':     'NGN',
        'redirect_url': url_for('negotiate.nego_callback', _external=True),
        'customer': {'email': current_user.email, 'name': current_user.username},
        'customizations': {
            'title':       'M World Luxury',
            'description': f'Negotiated price - {nego.product.name}',
        },
        'meta': {'negotiation_id': nego.id, 'tx_ref': tx_ref}
    }

    try:
        res  = requests.post('https://api.flutterwave.com/v3/payments',
                             headers=headers, json=payload, timeout=15)
        data = res.json()
        if data.get('status') == 'success':
            return jsonify({'payment_link': data['data']['link']})
        return jsonify({'error': data.get('message', 'Payment init failed')}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# User: payment callback for a negotiation
# ─────────────────────────────────────────
@negotiate.route('/negotiate/payment/callback')
@login_required
def nego_callback():
    status         = request.args.get('status')
    tx_ref         = request.args.get('tx_ref')
    transaction_id = request.args.get('transaction_id')

    nego_id = None
    try:
        nego_id = int(tx_ref.split('-')[2])
    except Exception:
        pass

    if status != 'successful' or not transaction_id or nego_id is None:
        flash('❌ Payment was not successful. Please try again.', 'danger')
        return redirect(url_for('negotiate.my_offers'))

    nego = Negotiation.query.get(nego_id)
    if not nego or nego.user_id != current_user.id:
        flash('Negotiation not found.', 'danger')
        return redirect(url_for('negotiate.my_offers'))

    if nego.status == 'paid':
        flash('This offer has already been paid.', 'info')
        return redirect(url_for('negotiate.my_offers'))

    secret_key = current_app.config.get('FLW_SECRET_KEY', '')
    headers    = {'Authorization': f'Bearer {secret_key}'}
    try:
        res  = requests.get(f'https://api.flutterwave.com/v3/transactions/{transaction_id}/verify',
                            headers=headers, timeout=15)
        data = res.json()
        txn  = data.get('data', {})

        if (data.get('status') == 'success'
                and txn.get('status') == 'successful'
                and txn.get('currency') == 'NGN'
                and float(txn.get('amount', 0)) >= nego.total_amount()):

            order = Order(user_id=current_user.id, status='Paid',
                          payment_ref=tx_ref, is_negotiated=True)
            db.session.add(order)
            db.session.flush()

            order_item = OrderItem(
                order_id=order.id,
                product_id=nego.product_id,
                quantity=nego.quantity,
                size=nego.size,
                price_each=nego.current_price()
            )
            db.session.add(order_item)

            if nego.product.stock >= nego.quantity:
                nego.product.stock -= nego.quantity

            nego.status = 'paid'
            db.session.commit()

            flash(f'🎉 Payment successful! Order #{order.id} confirmed at your negotiated price.', 'success')
            return redirect(url_for('cart.order_success', order_id=order.id))
        else:
            flash('❌ Payment verification failed. Contact support if you were charged.', 'danger')
            return redirect(url_for('negotiate.my_offers'))
    except Exception as e:
        flash(f'Verification error: {str(e)}', 'danger')
        return redirect(url_for('negotiate.my_offers'))


# ─────────────────────────────────────────
# ADMIN: view all negotiations
# ─────────────────────────────────────────
@negotiate.route('/admin/negotiations')
@login_required
def admin_negotiations():
    if not current_user.is_admin:
        flash('Admin access only.', 'danger')
        return redirect(url_for('admin.admin_login'))

    status_filter = request.args.get('status', 'all')
    query = Negotiation.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    offers = query.order_by(Negotiation.updated_at.desc()).all()

    wa_links = {}
    for o in offers:
        phone = o.user.phone
        if phone:
            phone = phone.lstrip('+').replace(' ', '')
            text = (f"Hi {o.user.username}, regarding your offer on "
                    f"'{o.product.name}' (Offer #{o.id})...")
            wa_links[o.id] = whatsapp_link(phone, text)

    counts = {
        'all':       Negotiation.query.count(),
        'pending':   Negotiation.query.filter_by(status='pending').count(),
        'countered': Negotiation.query.filter_by(status='countered').count(),
        'accepted':  Negotiation.query.filter_by(status='accepted').count(),
        'paid':      Negotiation.query.filter_by(status='paid').count(),
        'rejected':  Negotiation.query.filter_by(status='rejected').count(),
    }

    return render_template('admin_negotiations.html',
                           offers=offers, wa_links=wa_links,
                           counts=counts, status_filter=status_filter)


# ─────────────────────────────────────────
# ADMIN: respond to a negotiation
# action = accept | counter | reject
# ─────────────────────────────────────────
@negotiate.route('/admin/negotiations/respond/<int:nego_id>', methods=['POST'])
@login_required
def admin_respond(nego_id):
    if not current_user.is_admin:
        flash('Admin access only.', 'danger')
        return redirect(url_for('admin.admin_login'))

    nego    = Negotiation.query.get_or_404(nego_id)
    action  = request.form.get('action')
    message = request.form.get('admin_message', '').strip()

    if action == 'accept':
        nego.admin_price   = nego.offer_price
        nego.agreed_price  = nego.offer_price
        nego.status        = 'accepted'
        nego.admin_message = message or 'Offer accepted! You can proceed to payment.'
        flash(f'✅ Accepted offer #{nego.id}. Customer can now pay.', 'success')

    elif action == 'counter':
        try:
            counter_price = float(request.form.get('counter_price'))
            if counter_price <= 0:
                raise ValueError
        except (TypeError, ValueError):
            flash('Enter a valid counter price.', 'warning')
            return redirect(url_for('negotiate.admin_negotiations'))
        nego.admin_price   = counter_price
        nego.agreed_price  = None
        nego.status        = 'countered'
        nego.admin_message = message or f'We can offer ₦{counter_price:,.0f} each.'
        flash(f'💬 Counter price sent for offer #{nego.id}.', 'success')

    elif action == 'reject':
        nego.status        = 'rejected'
        nego.admin_message = message or 'Sorry, we cannot accept this offer.'
        flash(f'Offer #{nego.id} rejected.', 'info')

    else:
        flash('Unknown action.', 'warning')
        return redirect(url_for('negotiate.admin_negotiations'))

    db.session.commit()
    return redirect(url_for('negotiate.admin_negotiations'))
