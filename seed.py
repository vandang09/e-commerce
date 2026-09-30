from pathlib import Path

from app import create_app, db
from app.models import Category, Order, OrderItem, Product, Product3DModel, Review, Shop, User

app = create_app()

CATEGORIES = [
    ("Tech", "tech", "⌘"), ("Home", "home", "⌂"), ("Style", "style", "✳"),
    ("Beauty", "beauty", "✿"), ("Outdoors", "outdoors", "↟"), ("Kitchen", "kitchen", "◒"),
    ("Books", "books", "▤"), ("Audio", "audio", "♫"),
]
PRODUCTS = [
    ("Studio wireless headphones", "audio", 2490000, "SoundField", "photo-1505740420928-5e560c06d30e"),
    ("Everyday carry camera", "tech", 8950000, "Northstar", "photo-1516035069371-29a1b244cc32"),
    ("Ceramic pour-over set", "kitchen", 680000, "Sunday Objects", "photo-1495474472287-4d71bcdd2085"),
    ("Canvas weekend tote", "style", 420000, "Common Thread", "photo-1548036328-c9fa89d128fa"),
    ("Minimal desk lamp", "home", 1190000, "Form & Field", "photo-1507473885765-e6ed057f782c"),
    ("Field notes journal", "books", 185000, "Paper House", "photo-1531346878377-a5be20888e57"),
    ("Botanical face serum", "beauty", 355000, "Morrow Botanics", "photo-1608248543803-ba4f8c70ae0b"),
    ("Trail daypack 18L", "outdoors", 1450000, "Waymark", "photo-1553062407-98eeb64c6a62"),
]

with app.app_context():
    db.drop_all()
    db.create_all()
    categories = {}
    for name, slug, icon in CATEGORIES:
        category = Category(name=name, slug=slug, icon=icon)
        db.session.add(category)
        categories[slug] = category
    admin = User(username="admin", email="admin@example.com", full_name="Market Admin", role="admin")
    sellers = [
        User(username="seller", email="seller@example.com", full_name="Studio Seller", role="seller"),
        User(username="seller2", email="seller2@example.com", full_name="Field Seller", role="seller"),
        User(username="seller3", email="seller3@example.com", full_name="North Seller", role="seller"),
    ]
    customer = User(username="user", email="user@example.com", full_name="Demo Customer")
    demo_accounts = [(admin, "Admin@123"), (customer, "User@123")]
    demo_accounts.extend((seller, "Seller@123") for seller in sellers)
    for account, password in demo_accounts:
        account.set_password(password)
        db.session.add(account)
    db.session.flush()
    shop_details = [
        ("Sunday Supply", "sunday-supply", "Useful objects for slower, brighter days."),
        ("Northstar Goods", "northstar-goods", "Thoughtful tools and essentials for curious days."),
        ("Common Thread", "common-thread", "Well-made everyday pieces, chosen to last."),
    ]
    shops = []
    for seller, (name, slug, description) in zip(sellers, shop_details):
        shop = Shop(owner_id=seller.id, name=name, slug=slug, description=description)
        db.session.add(shop)
        shops.append(shop)
    db.session.flush()
    for index, (name, category, price, brand, image) in enumerate(PRODUCTS):
        for variation in range(3):
            title = name if variation == 0 else f"{name} · Edition {variation + 1}"
            db.session.add(Product(
                shop_id=shops[index % len(shops)].id, category_id=categories[category].id, name=title,
                slug=f"{name.lower().replace(' ', '-')}-{variation + 1}",
                description=f"Thoughtfully selected {name.lower()} made for everyday use. Designed with considered materials and a long life in mind.",
                price=price + variation * 90000, stock=12 + variation * 3,
                brand=brand, sold_count=38 - index + variation,
                image_url=f"https://images.unsplash.com/{image}?auto=format&fit=crop&w=900&q=85",
            ))
    db.session.flush()
    water_bottle = Product(
        shop_id=shops[0].id,
        category_id=categories["outdoors"].id,
        name="Trail-ready water bottle · 3D demo",
        slug="trail-ready-water-bottle-3d",
        description="A true interactive 3D product model from the Khronos glTF Sample Assets project. The model is CC0; product imagery and catalog copy are demo content.",
        price=320000,
        stock=18,
        brand="Khronos Sample",
        sold_count=12,
        image_url="https://images.unsplash.com/photo-1602143407151-7111542de6e8?auto=format&fit=crop&w=900&q=85",
        model_3d_url="/static/models/products/demo-water-bottle/WaterBottle.glb",
        model_3d_type="glb",
        has_3d=True,
    )
    db.session.add(water_bottle)
    db.session.flush()
    model_path = Path(app.static_folder) / "models" / "products" / "demo-water-bottle" / "WaterBottle.glb"
    db.session.add(Product3DModel(
        product_id=water_bottle.id,
        file_name="WaterBottle.glb",
        file_url=water_bottle.model_3d_url,
        file_size=model_path.stat().st_size,
        format="glb",
        is_active=True,
    ))
    reviewed_product = Product.query.order_by(Product.sold_count.desc()).first()
    demo_order = Order(
        user_id=customer.id,
        order_code="ORD-DEMO-2026",
        subtotal=reviewed_product.price,
        shipping_fee=0 if reviewed_product.price >= 500_000 else 25_000,
        total_amount=reviewed_product.price + (0 if reviewed_product.price >= 500_000 else 25_000),
        payment_method="mock",
        payment_status="paid",
        order_status="delivered",
        shipping_address="Demo address · Ho Chi Minh City",
    )
    db.session.add(demo_order)
    db.session.flush()
    db.session.add(OrderItem(
        order_id=demo_order.id,
        product_id=reviewed_product.id,
        shop_id=reviewed_product.shop_id,
        product_name=reviewed_product.name,
        price=reviewed_product.price,
        quantity=1,
        subtotal=reviewed_product.price,
    ))
    db.session.add(Review(
        user_id=customer.id,
        product_id=reviewed_product.id,
        order_id=demo_order.id,
        rating=5,
        comment="A thoughtful little upgrade to my everyday. Lovely quality and quick delivery.",
    ))
    db.session.commit()
    print("Seeded 5 demo accounts, 3 shops, 8 categories, 25 products including one true 3D GLB, and one delivered demo review.")
    print("Admin admin@example.com / Admin@123")
    print("Seller seller@example.com / Seller@123")
    print("Seller seller2@example.com / Seller@123")
    print("Seller seller3@example.com / Seller@123")
    print("Customer user@example.com / User@123")
