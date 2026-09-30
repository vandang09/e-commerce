from flask import Blueprint, abort, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from app.models import Category, Order, OrderItem, Product, ProductImage, Review, Shop

bp = Blueprint("storefront", __name__)
@bp.get("/")
def home():
    featured = Product.query.filter_by(status="approved").order_by(Product.sold_count.desc()).limit(8).all()
    newest = Product.query.filter_by(status="approved").order_by(Product.created_at.desc()).limit(8).all()
    shops = Shop.query.join(Product).distinct().limit(4).all()
    home_reviews = Review.query.order_by(Review.created_at.desc()).limit(3).all()
    return render_template(
        "home.html", featured=featured, newest=newest, shops=shops,
        home_reviews=home_reviews,
    )


@bp.get("/products")
def products():
    query = Product.query.filter_by(status="approved")
    term = request.args.get("q", "").strip()
    category_slug = request.args.get("category", "").strip()
    if term:
        pattern = f"%{term}%"
        query = query.filter(or_(Product.name.ilike(pattern), Product.brand.ilike(pattern)))
    if category_slug:
        query = query.join(Category).filter(Category.slug == category_slug)
    sort = request.args.get("sort", "newest")
    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort == "popular":
        query = query.order_by(Product.sold_count.desc())
    else:
        query = query.order_by(Product.created_at.desc())
    page = query.paginate(page=request.args.get("page", 1, type=int), per_page=12, error_out=False)
    return render_template("products.html", page=page, term=term, sort=sort)


@bp.get("/product/<slug>")
def product_detail(slug):
    product = Product.query.filter_by(slug=slug, status="approved").first_or_404()
    reviews = Review.query.filter_by(product_id=product.id).order_by(Review.created_at.desc()).all()
    rotation_images = [
        url_for("static", filename=frame.image_url)
        for frame in ProductImage.query.filter_by(product_id=product.id, image_type="360")
        .order_by(ProductImage.frame_index).all()
    ]
    review_order = None
    if current_user.is_authenticated:
        delivered_orders = Order.query.join(OrderItem).filter(
            Order.user_id == current_user.id,
            Order.order_status == "delivered",
            OrderItem.product_id == product.id,
        ).all()
        for order in delivered_orders:
            if not Review.query.filter_by(user_id=current_user.id, product_id=product.id, order_id=order.id).first():
                review_order = order
                break
    average_rating = sum(review.rating for review in reviews) / len(reviews) if reviews else None
    return render_template(
        "product_detail.html", product=product, reviews=reviews,
        rotation_images=rotation_images,
        average_rating=average_rating, review_order=review_order,
    )


@bp.get("/shop/<slug>")
def shop_detail(slug):
    shop = Shop.query.filter_by(slug=slug).first_or_404()
    products = Product.query.filter_by(shop_id=shop.id, status="approved").all()
    return render_template("shop.html", shop=shop, products=products)
