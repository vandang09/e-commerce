import secrets

from app import db
from app.models import CartItem, Order, OrderItem, Product


class CheckoutError(ValueError):
    pass


def place_order(user, shipping_address, payment_method="cod"):
    items = CartItem.query.filter_by(user_id=user.id).all()
    if not items:
        raise CheckoutError("Your cart is empty.")
    if not shipping_address.strip() or len(shipping_address.strip()) > 500:
        raise CheckoutError("Enter a valid shipping address.")
    if payment_method not in {"cod", "bank_transfer", "mock"}:
        raise CheckoutError("Choose a supported payment method.")

    subtotal = 0
    for item in items:
        product = db.session.get(Product, item.product_id)
        if product is None or product.status != "approved":
            raise CheckoutError("A product in your cart is no longer available.")
        if item.quantity < 1 or item.quantity > product.stock:
            raise CheckoutError(f"Not enough stock for {product.name}.")
        subtotal += product.price * item.quantity

    order = Order(
        user_id=user.id,
        order_code=f"ORD-{secrets.token_hex(4).upper()}",
        subtotal=subtotal,
        shipping_fee=0 if subtotal >= 500_000 else 25_000,
        total_amount=subtotal + (0 if subtotal >= 500_000 else 25_000),
        payment_method=payment_method,
        payment_status="paid" if payment_method == "mock" else "unpaid",
        shipping_address=shipping_address.strip(),
    )
    try:
        db.session.add(order)
        for item in items:
            product = db.session.get(Product, item.product_id)
            order.items.append(OrderItem(
                product_id=product.id,
                shop_id=product.shop_id,
                product_name=product.name,
                price=product.price,
                quantity=item.quantity,
                subtotal=product.price * item.quantity,
            ))
            product.stock -= item.quantity
            product.sold_count += item.quantity
            db.session.delete(item)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return order
