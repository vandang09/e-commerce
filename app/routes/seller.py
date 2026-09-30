import io
import secrets
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app import db
from app.models import Category, Order, OrderItem, Product, Product3DModel, ProductImage, Shop
from app.services.product_3d import Invalid3DModel, validate_3d_model
from app.utils import seller_required

bp = Blueprint("seller", __name__, url_prefix="/seller")


@bp.get("/")
@seller_required
def dashboard():
    shop = Shop.query.filter_by(owner_id=current_user.id).first()
    if not shop:
        shop = Shop(owner_id=current_user.id, name=f"{current_user.username}'s studio", slug=f"{current_user.username}-shop")
        db.session.add(shop)
        db.session.commit()
    product_count = Product.query.filter_by(shop_id=shop.id).count()
    order_count = OrderItem.query.filter_by(shop_id=shop.id).count()
    revenue = db.session.query(func.coalesce(func.sum(OrderItem.subtotal), 0)).join(Order).filter(
        OrderItem.shop_id == shop.id, Order.order_status != "cancelled"
    ).scalar()
    return render_template("seller/dashboard.html", shop=shop, product_count=product_count, order_count=order_count, revenue=revenue)


@bp.route("/products", methods=["GET", "POST"])
@seller_required
def products():
    shop = Shop.query.filter_by(owner_id=current_user.id).first()
    if not shop:
        return redirect(url_for("seller.dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", type=int)
        stock = request.form.get("stock", type=int)
        category = db.session.get(Category, request.form.get("category_id", type=int))
        if not name or not price or price < 1 or stock is None or stock < 0 or not category:
            flash("Complete every field with a valid price and stock amount.", "error")
        else:
            slug = f"{shop.slug}-{name.lower().replace(' ', '-')[:80]}-{Product.query.count() + 1}"
            product = Product(shop_id=shop.id, category_id=category.id, name=name, slug=slug,
                              description=request.form.get("description", "")[:4000], price=price,
                              stock=stock, brand=request.form.get("brand", "")[:80],
                              image_url=request.form.get("image_url", "")[:500], status="pending")
            db.session.add(product)
            db.session.commit()
            flash("Product submitted for review.", "success")
            return redirect(url_for("seller.products"))
    items = Product.query.filter_by(shop_id=shop.id).order_by(Product.created_at.desc()).all()
    return render_template("seller/products.html", products=items, categories=Category.query.order_by(Category.name).all())


@bp.get("/orders")
@seller_required
def orders():
    shop = Shop.query.filter_by(owner_id=current_user.id).first()
    items = OrderItem.query.filter_by(shop_id=shop.id).join(Order).order_by(Order.created_at.desc()).all() if shop else []
    return render_template("seller/orders.html", items=items)


@bp.post("/products/<int:product_id>/rotation-frames")
@seller_required
def upload_rotation_frames(product_id):
    shop = Shop.query.filter_by(owner_id=current_user.id).first()
    product = Product.query.filter_by(id=product_id, shop_id=shop.id if shop else -1).first_or_404()
    uploads = [item for item in request.files.getlist("frames") if item and item.filename]
    if not 24 <= len(uploads) <= 36:
        flash("Choose between 24 and 36 angle-ordered images for a full rotation.", "error")
        return redirect(url_for("seller.products"))

    upload_root = Path(current_app.config.get(
        "ROTATION_UPLOAD_DIR", Path(current_app.static_folder) / "uploads" / "rotation"
    ))
    folder = upload_root / str(product.id)
    folder.mkdir(parents=True, exist_ok=True)
    created_paths = []
    prepared_frames = []
    try:
        for frame_index, upload in enumerate(uploads, start=1):
            raw = upload.stream.read(2_000_001)
            if not raw or len(raw) > 2_000_000:
                raise ValueError("Each frame must be smaller than 2 MB.")
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Frames must be JPEG, PNG, or WebP images.")
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((1200, 1200))
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=82, method=5)
            filename = f"{frame_index:02d}-{secrets.token_hex(6)}.webp"
            path = folder / filename
            path.write_bytes(output.getvalue())
            created_paths.append(path)
            prepared_frames.append(ProductImage(
                product_id=product.id,
                image_url=f"uploads/rotation/{product.id}/{filename}",
                image_type="360",
                frame_index=frame_index,
            ))
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        for path in created_paths:
            path.unlink(missing_ok=True)
        flash(str(error) or "One or more frames could not be processed.", "error")
        return redirect(url_for("seller.products"))

    old_paths = [
        Path(current_app.static_folder) / frame.image_url
        for frame in ProductImage.query.filter_by(product_id=product.id, image_type="360").all()
    ]
    ProductImage.query.filter_by(product_id=product.id, image_type="360").delete(synchronize_session=False)
    db.session.add_all(prepared_frames)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise
    for path in old_paths:
        path.unlink(missing_ok=True)
    flash(f"Saved {len(prepared_frames)} optimized 360° frames.", "success")
    return redirect(url_for("seller.products"))


@bp.post("/products/<int:product_id>/rotation-frames/<int:frame_id>/delete")
@seller_required
def delete_rotation_frame(product_id, frame_id):
    shop = Shop.query.filter_by(owner_id=current_user.id).first()
    frame = ProductImage.query.join(Product).filter(
        ProductImage.id == frame_id,
        ProductImage.product_id == product_id,
        Product.shop_id == (shop.id if shop else -1),
    ).first_or_404()
    image_path = Path(current_app.static_folder) / frame.image_url
    db.session.delete(frame)
    remaining = ProductImage.query.filter_by(product_id=product_id, image_type="360").order_by(ProductImage.frame_index).all()
    db.session.flush()
    for frame_index, remaining_frame in enumerate(remaining, start=1):
        remaining_frame.frame_index = frame_index
    db.session.commit()
    image_path.unlink(missing_ok=True)
    flash("Rotation frame removed. Upload a complete set to restore the 360° view.", "info")
    return redirect(url_for("seller.products"))


@bp.post("/products/<int:product_id>/3d-model")
@seller_required
def upload_3d_model(product_id):
    shop = Shop.query.filter_by(owner_id=current_user.id).first()
    product_query = Product.query.filter_by(id=product_id)
    if current_user.role != "admin":
        product_query = product_query.filter_by(shop_id=shop.id if shop else -1)
    product = product_query.first_or_404()
    upload = request.files.get("model_3d_file")
    if not upload or not upload.filename:
        flash("Choose a GLB or self-contained glTF model.", "error")
        return redirect(url_for("seller.products"))

    original_name = secure_filename(upload.filename)
    extension = Path(original_name).suffix.lower()
    max_bytes = current_app.config["MAX_3D_MODEL_SIZE"]
    contents = upload.stream.read(max_bytes + 1)
    try:
        validate_3d_model(contents, extension, upload.mimetype, max_bytes)
    except Invalid3DModel as error:
        flash(str(error), "error")
        return redirect(url_for("seller.products"))

    upload_root = Path(current_app.config.get(
        "MODEL_UPLOAD_DIR", Path(current_app.static_folder) / "models" / "products"
    ))
    folder = upload_root / str(product.id)
    folder.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid4().hex}{extension}"
    file_path = folder / file_name
    relative_path = f"models/products/{product.id}/{file_name}"
    file_path.write_bytes(contents)

    try:
        for previous in product.models_3d:
            previous.is_active = False
        model_url = f"/static/{relative_path}"
        db.session.add(Product3DModel(
            product_id=product.id,
            file_name=original_name[:255],
            file_url=model_url,
            file_size=len(contents),
            format=extension.lstrip("."),
            is_active=True,
        ))
        product.model_3d_url = model_url
        product.model_3d_type = extension.lstrip(".")
        product.has_3d = True
        db.session.commit()
    except Exception:
        db.session.rollback()
        file_path.unlink(missing_ok=True)
        raise

    current_app.logger.info(
        "Seller %s uploaded a %s model for product %s (%s bytes)",
        current_user.id, extension, product.id, len(contents),
    )
    flash("3D model uploaded and set as the active showroom model.", "success")
    return redirect(url_for("seller.products"))


@bp.post("/products/<int:product_id>/3d-model/remove")
@seller_required
def remove_3d_model(product_id):
    shop = Shop.query.filter_by(owner_id=current_user.id).first()
    product_query = Product.query.filter_by(id=product_id)
    if current_user.role != "admin":
        product_query = product_query.filter_by(shop_id=shop.id if shop else -1)
    product = product_query.first_or_404()
    for model in product.models_3d:
        model.is_active = False
    product.has_3d = False
    product.model_3d_url = None
    product.model_3d_type = None
    db.session.commit()
    flash("3D model removed from the product page. The image gallery remains available.", "info")
    return redirect(url_for("seller.products"))


@bp.post("/orders/<int:item_id>/status")
@seller_required
def update_order_status(item_id):
    shop = Shop.query.filter_by(owner_id=current_user.id).first()
    item = OrderItem.query.filter_by(id=item_id, shop_id=shop.id if shop else -1).first_or_404()
    status = request.form.get("status")
    transitions = {"pending": {"confirmed"}, "confirmed": {"processing"}, "processing": {"shipped"}, "shipped": {"delivered"}}
    if status not in transitions.get(item.order.order_status, set()):
        flash("That order status change is not allowed.", "error")
    else:
        item.order.order_status = status
        db.session.commit()
        flash("Order status updated.", "success")
    return redirect(url_for("seller.orders"))
