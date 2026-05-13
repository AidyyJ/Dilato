# Dilato Agent Guide

This file is the working guide for future coding agents operating in this repository. It is repo-specific and should be treated as the primary operational reference for understanding the codebase, running it locally, deploying it, and avoiding known traps.

## 1. What This Project Is

Dilato is an Amazon-to-eBay reselling automation platform with three main parts:

- Backend API: FastAPI, SQLAlchemy 2.x async ORM, Alembic, PostgreSQL.
- Background processing: Celery workers and Celery Beat, backed by Redis.
- Operations dashboard: Next.js 16, React 19, Tailwind CSS 4, Recharts.

Core workflows supported by the codebase:

- Manage Amazon-sourced products.
- Create and publish eBay listings.
- Track eBay orders and fulfillment state.
- Record purchase cost and compute profit.
- Run periodic sync jobs through Celery.

The repository is a monorepo, but only the backend stack is containerized today. The dashboard is a separate Node.js app under `dashboard/` and must be started separately.

## 2. Repo Layout

Top-level directories of interest:

- `app/`: FastAPI app, services, models, schemas, Celery tasks.
- `alembic/`: database migrations.
- `tests/`: backend pytest suite.
- `dashboard/`: Next.js dashboard, Jest tests, Playwright tests.
- `docs/`: architecture, deployment, design, and original organizational agent docs.
- `scripts/`: container entrypoint and migration runner.

High-signal files:

- `app/main.py`: FastAPI app creation, router registration, auth protection.
- `app/core/config.py`: environment variable contract.
- `app/models/models.py`: database schema.
- `app/schemas/schemas.py`: API request/response contracts.
- `app/tasks/celery_app.py`: Celery app config and beat schedule.
- `docker-compose.yml`: local backend stack.
- `docker-compose.prod.yml`: production backend stack.
- `Dockerfile`: multi-stage Python image.
- `.env.example`: baseline environment template.

Existing agent-related docs:

- `docs/agents.md`: organizational role model, not a repo setup guide.
- `dashboard/AGENTS.md`: brief Next.js warning about version-specific behavior.

## 3. Runtime Architecture

### Backend

The FastAPI app mounts:

- Public routes:
  - `/api/v1/health`
  - `/api/v1/auth/*`
  - `/api/v1/orders/webhook`
- Protected routes requiring a valid JWT bearer token:
  - `/api/v1/products/*`
  - `/api/v1/listings/*`
  - `/api/v1/orders/*` except webhook
  - `/api/v1/pricing/*`
  - `/api/v1/sourcing/*`
  - `/api/v1/sync/*`

On startup, the app also runs `Base.metadata.create_all(...)` in addition to Alembic being used elsewhere. That is acceptable for local and single-node usage, but schema ownership should still be treated as Alembic-first.

### Database

Primary entities:

- `products`
- `listings`
- `orders`
- `price_history`
- `sync_log`
- `pricing_rules`
- `users`

The app uses `Decimal` and PostgreSQL `NUMERIC` for money-related fields.

### Background Tasks

Celery is configured with Redis as broker and result backend. Beat schedules recurring sync work for:

- Amazon product sync
- eBay listing sync
- eBay order sync
- Amazon price refresh
- Amazon stock sync

### Dashboard

The dashboard is a client-rendered Next.js app consuming the backend API through `dashboard/lib/api.ts`. The UI includes pages for:

- Dashboard analytics
- Products
- Listings
- Orders
- Pricing rules
- Profit analytics

Unit tests are in Jest, and end-to-end tests use Playwright with mocked API responses.

## 4. Current Reality: Known Gaps And Incomplete Work

Future agents should assume the following areas are incomplete, partially implemented, or mismatched with the docs:

1. Dashboard auth integration is missing.
   - The backend protects nearly all business routes with `get_current_active_user`.
   - The dashboard fetch client does not attach bearer tokens or implement login/session handling.
   - Consequence: the dashboard cannot operate end-to-end against the protected backend as written.

2. Sourcing is only partially realized.
   - `app/services/sourcing_service.py` still carries a TODO claiming the Amazon/eBay clients are unfinished.
   - The actual implementation now calls Amazon search, but eBay price estimation is still a local pricing-rule fallback, not a real market estimate from eBay completed sales or category data.
   - Consequence: sourcing exists, but it is not a fully market-aware arbitrage engine yet.

3. Profit trend data is limited by the current API contract.
   - The dashboard home page notes that `OrderProfitDetailOut` does not include order dates.
   - The chart therefore uses index-based placeholders like `Order 1`, `Order 2` instead of true daily aggregation.

4. Production env documentation is incomplete.
   - `docker-compose.prod.yml` expects `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`.
   - `.env.example` does not currently define those variables.
   - Consequence: production deployment from the template is incomplete unless those values are added manually.

5. The dashboard deployment story is incomplete in Docker.
   - Both compose files only define backend, worker, beat, db, and redis services.
   - There is no dashboard service, image, or reverse-proxy wiring for the frontend.

6. Celery beat has a duplicate price-sync alias.
   - `app/tasks/celery_app.py` schedules both `refresh-amazon-prices` and `sync-amazon-prices` on the same interval.
   - The design docs already note this should be cleaned up.

7. Some documentation is stale or boilerplate.
   - `dashboard/README.md` is still the default create-next-app README.
   - The deployment doc says the entrypoint script waits for PostgreSQL, but `scripts/entrypoint.sh` only runs migrations and starts the process; readiness coordination is currently coming from Docker Compose health/dependency behavior, not from the script itself.

## 5. Environment Variables

Required for the backend:

- `DATABASE_URL`
- `DATABASE_URL_SYNC`
- `SECRET_KEY`

Expected for real Amazon/eBay behavior:

- `AMAZON_ACCESS_KEY`
- `AMAZON_SECRET_KEY`
- `AMAZON_PARTNER_TAG`
- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`
- `EBAY_DEV_ID`
- `EBAY_RU_NAME`

Common optional values:

- `ALLOWED_ORIGINS`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_DB`
- `REDIS_PASSWORD`
- `PRICE_SYNC_INTERVAL`
- `STOCK_SYNC_INTERVAL`
- `DEFAULT_PROFIT_MARGIN_THRESHOLD`
- `DEFAULT_MAX_PRICE_USD`
- `DEFAULT_MIN_PRICE_USD`

Extra variables needed for production compose even though the template does not currently list them:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

## 6. Local Setup: Backend In Docker, Dashboard Separately

### A. Backend stack with Docker Compose

From the repo root:

```bash
cp .env.example .env
```

Fill in at least:

- `DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/reseller`
- `DATABASE_URL_SYNC=postgresql://postgres:postgres@db:5432/reseller`
- `SECRET_KEY=<strong-random-value>`

Optional but recommended even for local parity:

- `POSTGRES_USER=postgres`
- `POSTGRES_PASSWORD=postgres`
- `POSTGRES_DB=reseller`

Start the backend stack:

```bash
docker compose up --build -d
```

Useful checks:

```bash
docker compose ps
docker compose logs -f api
curl http://localhost:8000/api/v1/health
```

Manual migration commands:

```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic revision --autogenerate -m "description"
```

Useful worker commands:

```bash
docker compose logs -f worker
docker compose logs -f beat
docker compose exec worker celery -A app.tasks.celery_app inspect ping
```

### B. Dashboard for local testing

The dashboard is not part of the compose stack. Run it separately:

```bash
cd dashboard
npm ci
set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

On Linux/macOS:

```bash
export NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open:

- API docs: `http://localhost:8000/docs`
- Dashboard: `http://localhost:3000`

Important caveat:

- The live dashboard currently does not implement login/token handling, so it is not wired for authenticated use against the protected backend without additional work.
- Jest and Playwright coverage rely heavily on mocked API responses, so frontend test success does not prove full live integration.

## 7. Local Testing Commands

### Backend

Container-based test path:

```bash
docker compose exec api pytest
```

Non-Docker local path:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

### Dashboard

From `dashboard/`:

```bash
npm ci
npm test
npm run test:e2e
```

Note:

- The dashboard dependencies are not installed by default in a fresh checkout.
- If `node_modules` is missing, Jest and Playwright will not run until `npm ci` completes.

## 8. VPS Setup And Deployment

These instructions reflect the repo as it exists today.

### A. Provision the host

Install on the VPS:

- Docker Engine
- Docker Compose plugin
- Git
- Nginx or another reverse proxy
- Node.js 20+ if you intend to host the dashboard on the same machine

Open firewall ports:

- `22` for SSH
- `80` and `443` for HTTP/HTTPS

Prefer to keep `8000`, `5432`, and `6379` private to the host or internal network.

### B. Clone and configure

```bash
git clone <repo-url> /opt/dilato
cd /opt/dilato
cp .env.example .env
```

Edit `.env` and set at minimum:

- `SECRET_KEY` to a strong random value
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `DATABASE_URL=postgresql+asyncpg://<user>:<password>@db:5432/<db>`
- `DATABASE_URL_SYNC=postgresql://<user>:<password>@db:5432/<db>`
- `REDIS_PASSWORD` to a strong value
- real Amazon credentials if sourcing/price refresh is required
- real eBay credentials if listing/order sync is required
- `ALLOWED_ORIGINS` to the dashboard domain only

### C. Start the production backend stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Check status:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
curl http://127.0.0.1:8000/api/v1/health
```

Operational notes:

- The API container runs Alembic on startup through `scripts/entrypoint.sh`.
- Compose healthchecks are part of the intended startup sequencing.
- Outside Compose, the entrypoint itself does not wait for PostgreSQL readiness.

### D. Reverse proxy the backend

Terminate TLS in Nginx or your preferred proxy and forward to `127.0.0.1:8000`.

Recommended pattern:

- expose the FastAPI app only through the reverse proxy
- do not expose Postgres or Redis publicly
- lock down CORS to the frontend host

### E. Deploy the dashboard separately

There is no first-party production Docker setup for the dashboard in this repo. Use one of these approaches:

Option 1: run with Node.js directly

```bash
cd /opt/dilato/dashboard
npm ci
export NEXT_PUBLIC_API_URL=https://api.your-domain.tld
npm run build
npm run start -- -p 3000
```

Place it behind the same reverse proxy, for example:

- `https://app.your-domain.tld` -> `127.0.0.1:3000`
- `https://api.your-domain.tld` -> `127.0.0.1:8000`

Option 2: create a separate process manager unit

- systemd service for `npm run start`
- or `pm2` if your environment already standardizes on it

Important caveat:

- Until auth is implemented in the dashboard, a production deployment of the UI is mostly a shell over protected routes and will need additional integration work before it can function against the live secured API.

## 9. Recommended Agent Workflow

When working on this repo, use this order:

1. Confirm whether the change is backend, dashboard, infra, or docs.
2. Check whether the affected route is protected by auth.
3. Check whether the change touches an area already marked incomplete above.
4. Prefer focused validation:
   - backend: targeted pytest file or route tests
   - dashboard: targeted Jest file, then Playwright only if necessary
   - infra/docs: `docker compose config` or diff-based validation
5. Avoid broad refactors. This repo is compact and benefits from small, testable changes.

## 10. Common Commands

Repo root:

```bash
docker compose up --build -d
docker compose down
docker compose logs -f api
docker compose exec api pytest
docker compose exec api alembic upgrade head
```

Dashboard:

```bash
cd dashboard
npm ci
npm run dev
npm test
npm run test:e2e
```

## 11. Practical Warnings For Future Agents

- Do not assume the dashboard is fully integrated just because pages and tests exist.
- Do not assume the production env template is complete for `docker-compose.prod.yml`.
- Do not trust `dashboard/README.md` as project documentation; it is boilerplate.
- Do not remove Alembic ownership of schema changes even though startup also runs `create_all`.
- If you change auth behavior, check both the FastAPI router protection in `app/main.py` and the dashboard client in `dashboard/lib/api.ts`.
- If you change sourcing, verify whether the intended behavior is rule-based estimation or real eBay market lookup.
- If you change deployment docs, reconcile them with `scripts/entrypoint.sh`, not just with Compose behavior.

## 12. Short Status Snapshot

What appears production-capable today:

- backend API structure
- database schema and migrations
- Celery task framework
- Dockerized backend stack

What appears partially complete or still requiring integration work:

- dashboard authentication
- full live dashboard-to-API integration
- production-ready dashboard hosting path inside repo tooling
- advanced sourcing logic using real eBay market data
- cleanup of duplicate beat task alias and stale docs/comments

If you are a future agent, start by reading this file, then `README.md`, then the specific files in the area you are changing.