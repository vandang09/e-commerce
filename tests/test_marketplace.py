import io
import json
import struct
import pytest

from app import db
from app.models import Category, Order, OrderItem, Product, Product3DModel, ProductImage, Review, Shop, User
from PIL import Image
from app.services.product_3d import Invalid3DModel, validate_3d_model


def login(client, username, password):
    return client.post("/login", data={"identity": username, "password": password}, follow_redirects=True)


def make_minimal_glb():
    model_document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "buffers": [{"byteLength": 36}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}],
        "accessors": [{
            "bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
            "min": [-0.5, 0, 0], "max": [0.5, 1, 0],
        }],
    }
    json_chunk = json.dumps(model_document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    binary_chunk = struct.pack("<9f", -0.5, 0, 0, 0.5, 0, 0, 0, 1, 0)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    return (
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + struct.pack("<II", len(binary_chunk), 0x004E4942)
        + binary_chunk
    )


def test_gltf_validation_requires_self_contained_gltf_2():
    valid_document = json.dumps({
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "data:application/octet-stream;base64,AAAA", "byteLength": 3}],
    }).encode("utf-8")
    assert validate_3d_model(valid_document, ".gltf", "model/gltf+json", 1024)["asset"]["version"] == "2.0"

    external_reference = json.dumps({
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "../outside.bin", "byteLength": 3}],
    }).encode("utf-8")
    with pytest.raises(Invalid3DModel, match="self-contained"):
        validate_3d_model(external_reference, ".gltf", "model/gltf+json", 1024)

    with pytest.raises(Invalid3DModel, match="content type"):
        validate_3d_model(valid_document, ".gltf", "application/x-msdownload", 1024)


def test_register_and_login(client):
    response = client.post("/register", data={
        "username": "newbuyer", "email": "buyer@example.com", "password": "Market@123",
        "confirm_password": "Market@123",
    }, follow_redirects=True)
    assert response.status_code == 200
    client.post("/logout")
    response = login(client, "buyer@example.com", "Market@123")
    assert response.status_code == 200


def test_customer_cannot_access_admin(client, app):
    with app.app_context():
        user = User(username="buyer", email="buyer@example.com", full_name="Buyer")
        user.set_password("Market@123")
        db.session.add(user)
        db.session.commit()
    login(client, "buyer", "Market@123")
    assert client.get("/admin/").status_code == 403
    assert client.get("/admin/models").status_code == 403


def test_admin_can_open_model_registry(client, app):
    with app.app_context():
        admin = User(username="admin", email="admin@example.com", full_name="Admin", role="admin")
        admin.set_password("Market@123")
        db.session.add(admin)
        db.session.commit()
    login(client, "admin", "Market@123")
    response = client.get("/admin/models")
    assert response.status_code == 200
    assert b"Product 3D models" in response.data


def test_checkout_calculates_total_and_decrements_stock(client, app):
    with app.app_context():
        user = User(username="buyer", email="buyer@example.com", full_name="Buyer")
        user.set_password("Market@123")
        seller = User(username="seller", email="seller@example.com", full_name="Seller", role="seller")
        seller.set_password("Market@123")
        category = Category(name="Home", slug="home")
        db.session.add_all([user, seller, category])
        db.session.flush()
        shop = Shop(owner_id=seller.id, name="Test Shop", slug="test-shop")
        db.session.add(shop)
        db.session.flush()
        product = Product(shop_id=shop.id, category_id=category.id, name="Lamp", slug="lamp", price=100000, stock=4)
        db.session.add(product)
        db.session.commit()
        product_id = product.id
        user_id = user.id
    login(client, "buyer", "Market@123")
    invalid_quantity = client.post("/api/cart/add", json={"product_id": product_id, "quantity": "2"})
    assert invalid_quantity.status_code == 400
    client.post("/api/cart/add", json={"product_id": product_id, "quantity": 2})
    response = client.post("/checkout", data={
        "shipping_address": "12 Market Street", "payment_method": "cod", "total_amount": "1",
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Product, product_id).stock == 2
        order = Order.query.one()
        assert order.subtotal == 200000
        assert order.total_amount == 225000


def test_seller_only_sees_own_products(client, app):
    with app.app_context():
        seller = User(username="seller", email="seller@example.com", full_name="Seller", role="seller")
        other = User(username="other", email="other@example.com", full_name="Other", role="seller")
        seller.set_password("Market@123")
        other.set_password("Market@123")
        category = Category(name="Home", slug="home")
        db.session.add_all([seller, other, category])
        db.session.flush()
        own_shop = Shop(owner_id=seller.id, name="Own Shop", slug="own-shop")
        other_shop = Shop(owner_id=other.id, name="Other Shop", slug="other-shop")
        db.session.add_all([own_shop, other_shop])
        db.session.flush()
        db.session.add_all([
            Product(shop_id=own_shop.id, category_id=category.id, name="Visible lamp", slug="visible-lamp", price=100, stock=1),
            Product(shop_id=other_shop.id, category_id=category.id, name="Private lamp", slug="private-lamp", price=100, stock=1),
        ])
        db.session.commit()
    login(client, "seller", "Market@123")
    response = client.get("/seller/products")
    assert response.status_code == 200
    assert b"Visible lamp" in response.data
    assert b"Private lamp" not in response.data


def test_review_requires_delivered_order_and_appears_on_product(client, app):
    with app.app_context():
        buyer = User(username="buyer", email="buyer@example.com", full_name="Buyer")
        seller = User(username="seller", email="seller@example.com", full_name="Seller", role="seller")
        buyer.set_password("Market@123")
        seller.set_password("Market@123")
        category = Category(name="Home", slug="home")
        db.session.add_all([buyer, seller, category])
        db.session.flush()
        shop = Shop(owner_id=seller.id, name="Test Shop", slug="test-shop")
        db.session.add(shop)
        db.session.flush()
        product = Product(shop_id=shop.id, category_id=category.id, name="Desk lamp", slug="desk-lamp", price=100, stock=1)
        db.session.add(product)
        db.session.flush()
        order = Order(user_id=buyer.id, order_code="ORD-DELIVERED", subtotal=100, shipping_fee=0,
                      total_amount=100, shipping_address="One Market Street", order_status="pending")
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, product_id=product.id, shop_id=shop.id,
                                 product_name=product.name, price=100, quantity=1, subtotal=100))
        db.session.commit()
        product_id = product.id
        order_id = order.id
    login(client, "buyer", "Market@123")
    payload = {"product_id": product_id, "rating": "5", "comment": "A lovely lamp."}
    assert client.post("/reviews/create", data=payload).status_code == 403
    with app.app_context():
        db.session.get(Order, order_id).order_status = "delivered"
        db.session.commit()
    assert b"Share your review" in client.get("/product/desk-lamp").data
    assert client.post("/reviews/create", data=payload).status_code == 302
    with app.app_context():
        assert Review.query.one().comment == "A lovely lamp."
    assert b"A lovely lamp." in client.get("/product/desk-lamp").data


def test_rotation_upload_is_optimized_and_shop_scoped(client, app):
    with app.app_context():
        seller = User(username="seller", email="seller@example.com", full_name="Seller", role="seller")
        other = User(username="other", email="other@example.com", full_name="Other", role="seller")
        seller.set_password("Market@123")
        other.set_password("Market@123")
        category = Category(name="Tech", slug="tech")
        db.session.add_all([seller, other, category])
        db.session.flush()
        own_shop = Shop(owner_id=seller.id, name="Own Shop", slug="own-shop")
        other_shop = Shop(owner_id=other.id, name="Other Shop", slug="other-shop")
        db.session.add_all([own_shop, other_shop])
        db.session.flush()
        own_product = Product(shop_id=own_shop.id, category_id=category.id, name="Own camera", slug="own-camera", price=100, stock=2)
        other_product = Product(shop_id=other_shop.id, category_id=category.id, name="Other camera", slug="other-camera", price=100, stock=2)
        db.session.add_all([own_product, other_product])
        db.session.commit()
        own_product_id = own_product.id
        other_product_id = other_product.id
    login(client, "seller", "Market@123")
    frame_buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "#dc7258").save(frame_buffer, format="PNG")
    frame_bytes = frame_buffer.getvalue()

    denied_files = [(io.BytesIO(frame_bytes), f"frame-{index}.png") for index in range(24)]
    denied = client.post(
        f"/seller/products/{other_product_id}/rotation-frames",
        data={"frames": denied_files}, content_type="multipart/form-data",
    )
    assert denied.status_code == 404

    short_set = [(io.BytesIO(frame_bytes), f"frame-{index}.png") for index in range(23)]
    rejected = client.post(
        f"/seller/products/{own_product_id}/rotation-frames",
        data={"frames": short_set}, content_type="multipart/form-data",
    )
    assert rejected.status_code == 302

    uploads = [(io.BytesIO(frame_bytes), f"frame-{index}.png") for index in range(24)]
    response = client.post(
        f"/seller/products/{own_product_id}/rotation-frames",
        data={"frames": uploads}, content_type="multipart/form-data",
    )
    assert response.status_code == 302
    with app.app_context():
        frames = ProductImage.query.filter_by(product_id=own_product_id).order_by(ProductImage.frame_index).all()
        assert len(frames) == 24
        assert [frame.frame_index for frame in frames] == list(range(1, 25))
        assert frames[0].image_url.endswith(".webp")
        first_frame_id = frames[0].id
    product_page = client.get("/product/own-camera")
    assert product_page.status_code == 200
    assert b"24 optimized angles" in product_page.data
    deleted = client.post(f"/seller/products/{own_product_id}/rotation-frames/{first_frame_id}/delete")
    assert deleted.status_code == 302
    with app.app_context():
        remaining_indexes = [
            frame.frame_index for frame in ProductImage.query.filter_by(product_id=own_product_id)
            .order_by(ProductImage.frame_index).all()
        ]
        assert remaining_indexes == list(range(1, 24))


def test_3d_model_upload_versioning_and_fallback(client, app):
    with app.app_context():
        seller = User(username="seller", email="seller@example.com", full_name="Seller", role="seller")
        other = User(username="other", email="other@example.com", full_name="Other", role="seller")
        seller.set_password("Market@123")
        other.set_password("Market@123")
        category = Category(name="Tech", slug="tech")
        db.session.add_all([seller, other, category])
        db.session.flush()
        own_shop = Shop(owner_id=seller.id, name="Own Shop", slug="own-shop")
        other_shop = Shop(owner_id=other.id, name="Other Shop", slug="other-shop")
        db.session.add_all([own_shop, other_shop])
        db.session.flush()
        own_product = Product(shop_id=own_shop.id, category_id=category.id, name="3D Speaker", slug="3d-speaker", price=100, stock=2)
        other_product = Product(shop_id=other_shop.id, category_id=category.id, name="Other Speaker", slug="other-speaker", price=100, stock=2)
        db.session.add_all([own_product, other_product])
        db.session.commit()
        own_product_id = own_product.id
        other_product_id = other_product.id
    login(client, "seller", "Market@123")
    model_bytes = make_minimal_glb()

    denied = client.post(
        f"/seller/products/{other_product_id}/3d-model",
        data={"model_3d_file": (io.BytesIO(model_bytes), "model.glb", "model/gltf-binary")},
        content_type="multipart/form-data",
    )
    assert denied.status_code == 404

    invalid = client.post(
        f"/seller/products/{own_product_id}/3d-model",
        data={"model_3d_file": (io.BytesIO(b"not a model"), "model.glb", "model/gltf-binary")},
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 302

    for model_name in ["speaker.glb", "speaker-revision.glb"]:
        uploaded = client.post(
            f"/seller/products/{own_product_id}/3d-model",
            data={"model_3d_file": (io.BytesIO(model_bytes), model_name, "model/gltf-binary")},
            content_type="multipart/form-data",
        )
        assert uploaded.status_code == 302
    with app.app_context():
        product = db.session.get(Product, own_product_id)
        versions = Product3DModel.query.filter_by(product_id=own_product_id).order_by(Product3DModel.id).all()
        assert product.has_3d is True
        assert product.model_3d_type == "glb"
        assert product.model_3d_url.startswith("/static/models/products/")
        assert [version.is_active for version in versions] == [False, True]
        assert versions[-1].file_size == len(model_bytes)
    product_page = client.get("/product/3d-speaker")
    assert product_page.status_code == 200
    assert b"3D showroom" in product_page.data
    assert b"data-3d-model-data" in product_page.data
    assert b"https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js" in product_page.data

    removed = client.post(f"/seller/products/{own_product_id}/3d-model/remove")
    assert removed.status_code == 302
    with app.app_context():
        product = db.session.get(Product, own_product_id)
        assert product.has_3d is False
        assert product.model_3d_url is None
        assert not Product3DModel.query.filter_by(product_id=own_product_id, is_active=True).count()
    fallback_page = client.get("/product/3d-speaker")
    assert b"data-3d-model-data" not in fallback_page.data
    assert b"data-three-canvas" not in fallback_page.data
    assert b"data-open-spin" not in fallback_page.data
