# Morrow Market

A small, runnable Flask marketplace demo built with Python, Flask, SQLite, Jinja, CSS, and vanilla JavaScript. It uses an application factory, SQLAlchemy models, blueprints, a checkout service, CSRF protection, and role checks. The visual identity and sample catalog are original demo content.

## Requirements

- Python 3.9+
- pip

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python seed.py
python run.py
```

Open http://127.0.0.1:5000. On macOS/Linux, activate with `source .venv/bin/activate` and copy the environment file with `cp .env.example .env`.

The app creates its SQLite database under `instance/` on first run. `seed.py` resets that database before inserting the demo catalog, a delivered sample order, and its verified review.

## Demo accounts

| Role | Email | Username | Password |
| --- | --- | --- | --- |
| Admin | admin@example.com | admin | Admin@123 |
| Seller | seller@example.com | seller | Seller@123 |
| Seller | seller2@example.com | seller2 | Seller@123 |
| Seller | seller3@example.com | seller3 | Seller@123 |
| Customer | user@example.com | user | User@123 |

Change the demo passwords and set a stable, random `SECRET_KEY` in `.env` before deploying anywhere accessible to others. If unset locally, the app generates a temporary key that changes after a restart. Enable `SESSION_COOKIE_SECURE=true` behind HTTPS.

## Included demo flows

- Customer registration, login, logout, product discovery, category filters, search, sorting, wishlist, and cart.
- Checkout with server-side price, stock, shipping, and order calculations; COD, bank transfer, and a mock paid payment option.
- Order history and order detail; seller shop/product/order management with shop ownership checks.
- Product reviews gated on a delivered order, plus review display on the product page.
- Product detail image/360° mode switch, keyboard/pointer/touch rotation, inertia, opt-in auto-rotate, bounded zoom, fullscreen, and progressive frame loading. Seller-owned products accept 24–36 ordered JPEG/PNG/WebP frames, validated and optimized to WebP.
- Optional true Three.js/WebGL showroom for uploaded glTF 2.0 GLB or self-contained GLTF models, with OrbitControls, model auto-fit, responsive quality, showroom lighting, keyboard, auto-rotate, reset, fullscreen, and image fallback. Sellers manage their own models; admins have a catalog-wide model registry.
- Admin overview, account enable/disable, and moderation of seller-submitted products.
- CSRF-protected forms and JSON mutations, password hashing, role authorization, paginated catalog/account/order listings, and responsive pages.

Three.js is loaded as pinned ES modules from jsDelivr for this demo, so model viewing needs a network connection; the product page catches module/WebGL/model failures and retains its image view. The seeded catalog includes a real CC0 GLB water-bottle model on `/product/trail-ready-water-bottle-3d`; see `app/static/models/ATTRIBUTION.md` for its source and license. Upload another model from Seller studio (under 50 MB), or place a self-contained `.glb`/`.gltf` beneath `app/static/models/products/<product-id>/` and set `model_3d_url`, `model_3d_type`, and `has_3d` on that product. Draco-compressed meshes are supported through the versioned Google decoder CDN. External glTF buffer/image paths are rejected for upload; embed them or use GLB.

External payment gateways, live shipping quotes, standard product uploads, seller analytics charts, saved delivery addresses, voucher redemption, notifications, and production deployment hardening are not implemented in this demo. Other seed products use the image fallback until a seller uploads an optional true 3D model or 24–36 real angle frames. Payment methods are simulations and do not collect payment credentials.

## Tests

```powershell
python -m pytest -q
```

The tests cover account registration/login, customer-to-admin authorization, and checkout totals/stock changes. The app uses SQLite through SQLAlchemy, so another SQL database can be configured with a compatible `DATABASE_URL` and driver without changing model-level business logic.

## Run with Docker

Install and start Docker Desktop, then create a local environment file and set a unique `SECRET_KEY` in it:

```powershell
Copy-Item .env.example .env
```

Build and start the production Waitress container:

```powershell
docker compose up --build -d
docker compose ps
```

Open http://127.0.0.1:5000. The container listens only on the host's loopback interface by default. Set `APP_PORT` in `.env` to use another local port. SQLite data, logs, seller uploads, and uploaded 3D models are stored in named Docker volumes and survive container rebuilds. To stop the app, run `docker compose down`; to also permanently delete its stored data, run `docker compose down --volumes`.

## Cloudflare Tunnel + Workers VPC

The optional deployment keeps Flask and SQLite on an always-on Windows host. Waitress listens only on loopback; a Cloudflare Tunnel connector on that same host makes the origin privately reachable, and a Cloudflare Worker with a VPC Service binding is the public HTTPS gateway:

```text
Browser → Worker (workers.dev or your domain) → VPC Service → Tunnel → 127.0.0.1:5000
```

Follow [cloudflare/worker/README.md](cloudflare/worker/README.md) for the setup. Workers VPC is currently in beta; Cloudflare documents it as available on Workers plans. Creating tunnels and VPC services requires the Cloudflare Connectivity Directory Admin role; binding/deploying requires Connectivity Directory Bind or Admin. Keep the tunnel token, `.env`, and account IDs private.