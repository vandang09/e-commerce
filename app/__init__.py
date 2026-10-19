import os
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config.get("TRUST_PROXY_HEADERS"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    log_dir = Path(app.root_path).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    if not any(getattr(handler, "baseFilename", None) == str(log_path) for handler in app.logger.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    csrf.init_app(app)

    from app import models
    from app.routes import admin, auth, commerce, seller, storefront

    app.register_blueprint(auth.bp)
    app.register_blueprint(storefront.bp)
    app.register_blueprint(commerce.bp)
    app.register_blueprint(seller.bp)
    app.register_blueprint(admin.bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    @app.context_processor
    def inject_market_data():
        from app.models import CartItem, Category
        from flask_login import current_user

        categories = Category.query.order_by(Category.name).all()
        cart_count = (
            sum(item.quantity for item in current_user.cart_items)
            if current_user.is_authenticated
            else 0
        )
        return {"nav_categories": categories, "cart_count": cart_count}

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        app.logger.exception("Unhandled application error")
        return render_template("errors/500.html"), 500

    with app.app_context():
        db.create_all()
        product_columns = {column["name"] for column in inspect(db.engine).get_columns("products")}
        schema_updates = {
            "model_3d_url": "VARCHAR(500)",
            "model_3d_type": "VARCHAR(20)",
            "has_3d": "BOOLEAN NOT NULL DEFAULT 0",
        }
        with db.engine.begin() as connection:
            for column_name, column_type in schema_updates.items():
                if column_name not in product_columns:
                    connection.execute(text(f"ALTER TABLE products ADD COLUMN {column_name} {column_type}"))

    return app
