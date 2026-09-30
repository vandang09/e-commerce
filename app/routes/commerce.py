from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app import db
from app.models import CartItem, Order, OrderItem, Product, Review, Wishlist
from app.services.checkout import CheckoutError, place_order

bp = Blueprint("commerce", __name__)


def json_error(message, status=400):
    return jsonify(success=False, message=message), status


@bp.get("/cart")
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    return render_template("cart.html", items=items)


@bp.post("/api/cart/add")
@login_required
def add_cart():
    data = request.get_json(silent=True)
    if data is None:
        product_id = request.form.get("product_id", type=int)
        quantity = request.form.get("quantity", 1, type=int)
    else:
        product_id = data.get("product_id")
        quantity = data.get("quantity", 1)
    product = db.session.get(Product, product_id)
    if not product or product.status != "approved":
        return json_error("Product is unavailable.", 404)
    if type(quantity) is not int or quantity < 1 or quantity > product.stock:
        return json_error("Requested quantity is unavailable.")
    item = CartItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if item:
        if item.quantity + quantity > product.stock:
            return json_error("There is not enough stock for that quantity.")
        item.quantity += quantity
    else:
        db.session.add(CartItem(user_id=current_user.id, product_id=product.id, quantity=quantity))
    db.session.commit()
    count = sum(row.quantity for row in current_user.cart_items)
    return jsonify(success=True, message="Added to your bag.", cart_count=count)


@bp.post("/api/cart/update")
@login_required
def update_cart():
    data = request.get_json(silent=True) or {}
    item = db.session.get(CartItem, data.get("item_id"))
    quantity = data.get("quantity")
    if not item or item.user_id != current_user.id:
        return json_error("Cart item not found.", 404)
    if not isinstance(quantity, int) or quantity < 1 or quantity > item.product.stock:
        return json_error("Choose a quantity available in stock.")
    item.quantity = quantity
    db.session.commit()
    count = sum(row.quantity for row in current_user.cart_items)
    return jsonify(success=True, subtotal=item.product.price * quantity, cart_count=count)


@bp.post("/api/cart/remove")
@login_required
def remove_cart():
    data = request.get_json(silent=True) or {}
    item = db.session.get(CartItem, data.get("item_id"))
    if not item or item.user_id != current_user.id:
        return json_error("Cart item not found.", 404)
    db.session.delete(item)
    db.session.commit()
    count = sum(row.quantity for row in current_user.cart_items)
    return jsonify(success=True, message="Removed from your bag.", cart_count=count)


@bp.post("/api/wishlist/toggle")
@login_required
def toggle_wishlist():
    data = request.get_json(silent=True) or {}
    product = db.session.get(Product, data.get("product_id"))
    if not product or product.status != "approved":
        return json_error("Product is unavailable.", 404)
    saved = Wishlist.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if saved:
        db.session.delete(saved)
        active = False
    else:
        db.session.add(Wishlist(user_id=current_user.id, product_id=product.id))
        active = True
    db.session.commit()
    return jsonify(success=True, active=active)


@bp.get("/wishlist")
@login_required
def wishlist():
    saved = Wishlist.query.filter_by(user_id=current_user.id).all()
    return render_template("wishlist.html", saved=saved)


@bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if request.method == "POST":
        try:
            order = place_order(
                current_user,
                request.form.get("shipping_address", ""),
                request.form.get("payment_method", "cod"),
            )
        except CheckoutError as error:
            flash(str(error), "error")
        else:
            flash("Order placed successfully.", "success")
            return redirect(url_for("commerce.order_detail", order_code=order.order_code))
    return render_template("checkout.html", items=items)


@bp.get("/orders")
@login_required
def orders():
    status = request.args.get("status", "")
    query = Order.query.filter_by(user_id=current_user.id)
    if status:
        query = query.filter_by(order_status=status)
    page = query.order_by(Order.created_at.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=10, error_out=False)
    return render_template("orders.html", page=page, status=status)


@bp.get("/orders/<order_code>")
@login_required
def order_detail(order_code):
    order = Order.query.filter_by(order_code=order_code, user_id=current_user.id).first_or_404()
    return render_template("order_detail.html", order=order)


@bp.post("/reviews/create")
@login_required
def create_review():
    product_id = request.form.get("product_id", type=int)
    order = db.session.execute(
        select(Order).join(Order.items).where(
            Order.user_id == current_user.id,
            Order.order_status == "delivered",
            OrderItem.product_id == product_id,
        )
    ).scalar_one_or_none()
    if not order:
        abort(403)
    if Review.query.filter_by(user_id=current_user.id, product_id=product_id, order_id=order.id).first():
        flash("You have already reviewed this purchase.", "info")
        return redirect(url_for("commerce.order_detail", order_code=order.order_code))
    rating = request.form.get("rating", type=int)
    if rating not in range(1, 6):
        flash("Choose a rating from 1 to 5.", "error")
    else:
        db.session.add(Review(user_id=current_user.id, product_id=product_id, order_id=order.id, rating=rating, comment=request.form.get("comment", "")[:1000]))
        db.session.commit()
        flash("Thanks for sharing your review.", "success")
    return redirect(url_for("commerce.order_detail", order_code=order.order_code))
