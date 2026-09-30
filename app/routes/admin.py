from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from app import db
from app.models import Order, Product, Shop, User
from app.utils import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@admin_required
def dashboard():
    metrics = {
        "users": User.query.count(),
        "sellers": User.query.filter_by(role="seller").count(),
        "products": Product.query.count(),
        "orders": Order.query.count(),
        "revenue": db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(Order.order_status != "cancelled").scalar(),
    }
    pending = Product.query.filter_by(status="pending").order_by(Product.created_at.desc()).all()
    return render_template("admin/dashboard.html", metrics=metrics, pending=pending)


@bp.get("/users")
@admin_required
def users():
    term = request.args.get("q", "").strip()
    query = User.query
    if term:
        query = query.filter(User.username.ilike(f"%{term}%") | User.email.ilike(f"%{term}%"))
    page = query.order_by(User.created_at.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=20, error_out=False)
    return render_template("admin/users.html", page=page)


@bp.get("/models")
@admin_required
def models():
    page = Product.query.join(Shop).order_by(Product.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, error_out=False
    )
    return render_template("admin/models.html", page=page)


@bp.post("/users/<int:user_id>/toggle")
@admin_required
def toggle_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot disable your own account.", "error")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        flash("Account access updated.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/products/<int:product_id>/approve")
@admin_required
def approve_product(product_id):
    product = db.get_or_404(Product, product_id)
    product.status = "approved" if request.form.get("action") == "approve" else "rejected"
    db.session.commit()
    flash("Product review saved.", "success")
    return redirect(url_for("admin.dashboard"))
