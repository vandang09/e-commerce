# Morrow Market: Cloudflare Tunnel + Workers VPC

This deploys Flask/SQLite on an always-on Windows host. The origin binds to loopback only. `cloudflared` connects that host to Cloudflare; a Worker with a VPC Service binding is the public HTTPS entry point. The browser never connects directly to the origin.

```text
Browser → Worker (workers.dev/custom domain) → VPC Service → Tunnel → 127.0.0.1:5000
```

Workers VPC is currently beta. Cloudflare documents availability on Workers plans. Creating a Tunnel and VPC Service needs the **Connectivity Directory Admin** role. Binding/deploying the Worker needs **Connectivity Directory Bind** or Admin. The Worker Service ID is an account-specific value; replace the placeholder in `wrangler.jsonc` locally. Do not commit tunnel tokens or `.env` files.

## 1. Prepare the Flask origin

From PowerShell at the repository root, create/activate the virtual environment if needed and install the updated requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a persistent random `SECRET_KEY` in `.env`, then set these production values there:

```dotenv
SESSION_COOKIE_SECURE=true
TRUST_PROXY_HEADERS=true
DATABASE_URL=sqlite:///ecommerce.db
```

Keep the SQLite `instance/` directory on persistent local storage and back it up. Do not run `seed.py` on a database with real data; it resets the database. If this is a fresh install, seed once with `python seed.py`.

Stop any existing `python run.py` development server. In one terminal, start the production WSGI server bound only to localhost:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5000 run:app
```

Check locally at `http://127.0.0.1:5000`. Leave this process running. The machine must remain powered on and connected for the site to stay available.

## 2. Create and run a Cloudflare Tunnel

In Cloudflare Zero Trust, open **Workers VPC → Tunnels → Create**. Create a tunnel, select Windows, and install the provided `cloudflared` connector command on the same machine as Waitress. Keep the dashboard-provided tunnel token private. Run the connector as a Windows service for persistence, or test it in a second PowerShell terminal using the command Cloudflare provides, typically:

```powershell
cloudflared.exe tunnel run --token $env:TUNNEL_TOKEN
```

Set `$env:TUNNEL_TOKEN` locally in that terminal; never paste it into chat or commit it. The connector needs to reach `127.0.0.1:5000`. Do not create a public Tunnel hostname route for the origin; the Worker/VPC path is the intended ingress.

## 3. Create a VPC Service for Flask

In **Workers VPC → VPC Services → Create**, register an HTTP service:

- Tunnel: the tunnel created in the previous step
- Host/IP: `127.0.0.1`
- HTTP port: `5000`
- HTTPS port: leave unused

Save the service and copy its Service ID. The origin hop is plain HTTP on loopback only; the Worker-to-Cloudflare path is encrypted by Tunnel. Do not bind Waitress to a public interface.

## 4. Configure and test the Worker

Edit `cloudflare/worker/wrangler.jsonc` and replace `REPLACE_WITH_CLOUDFLARE_VPC_SERVICE_ID` with your VPC Service ID. Install Wrangler dependencies and log in:

```powershell
Set-Location cloudflare/worker
npm install
npx wrangler login
npx wrangler dev
```

Wrangler uses the `remote: true` VPC binding to test against the Cloudflare VPC Service. Open the local Wrangler URL (usually `http://localhost:8787`) and test product pages, login cookies, cart POSTs, uploads, and the 3D model. Keep the Waitress and `cloudflared` processes running during this test.

## 5. Deploy

```powershell
npx wrangler deploy
```

The Worker is available on the account's `workers.dev` hostname. To use your own hostname, add it as a Worker custom domain in the Cloudflare dashboard (or configure a route in Wrangler). This exposes the Worker, not the Flask origin. Set any final domain/route before turning on production traffic.

## Configuration notes

- The Worker forwards all paths, methods, bodies, and response headers to Flask, and sets trusted `X-Forwarded-*` headers. Flask's `ProxyFix` is enabled only when `TRUST_PROXY_HEADERS=true`.
- `SESSION_COOKIE_SECURE=true` assumes users reach the Worker over HTTPS.
- VPC binding/Service APIs may change while Workers VPC is beta. Refer to the official [Workers VPC setup](https://developers.cloudflare.com/workers-vpc/get-started/), [VPC Services](https://developers.cloudflare.com/workers-vpc/configuration/vpc-services/), and [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/) docs.
- This project uses SQLite for a small demo deployment. Back up the database and static uploads/models. For a multi-instance production service, move to a supported managed database and shared object storage before scaling out.
