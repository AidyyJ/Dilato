# Amazon-to-eBay Reselling Automation — Technical Design Document

**Version:** 1.0  
**Date:** 2026-05-11  
**Status:** Approved  
**Issue:** [CPRAA-107](/CPRAA/issues/CPRAA-107)

---

## 1. Executive Summary

This document describes the architecture and technical design of the **Amazon-to-eBay Reselling Automation** platform. The system automates the core workflows of online arbitrage: sourcing products from Amazon, listing them on eBay, syncing prices and stock, ingesting eBay orders, tracking purchase costs, and calculating profit margins.

The platform consists of:
- A **FastAPI** backend with async PostgreSQL (SQLAlchemy 2.0), Celery background workers, and Redis.
- A **Next.js 16** dashboard (React 19, Tailwind CSS, Recharts) for operations and analytics.
- Containerised deployment via **Docker Compose** (local) and **Docker** (production).

---

## 2. Goals & Non-Goals

### Goals
- Automate product sourcing from Amazon PA-API and creation of eBay listings.
- Maintain real-time(ish) price and stock parity between Amazon source and eBay listings.
- Ingest eBay orders via webhooks and API polling, then track fulfillment and profit.
- Provide a web dashboard for managing products, listings, orders, pricing rules, and profit analytics.
- Operate reliably in the face of external API rate limits, transient failures, and credential expiry.

### Non-Goals
- Marketplace expansion beyond eBay US (site ID `0`) in the initial release.
- Automated purchasing on Amazon (manual purchase URL generation only).
- Multi-tenant SaaS (single-user/single-reseller deployment).
- Native mobile apps.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Client Layer                                │
│  ┌──────────────┐                                                       │
│  │  Next.js 16  │  Dashboard (React 19, Tailwind, Recharts)             │
│  │   (Port 3000)│  → JWT Bearer auth, fetch with retry + backoff       │
│  └──────┬───────┘                                                       │
└─────────┼───────────────────────────────────────────────────────────────┘
          │ HTTPS / CORS
┌─────────▼───────────────────────────────────────────────────────────────┐
│                            API Layer                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  FastAPI 0.1.0 (Python 3.13)                                    │    │
│  │  • Rate limiting (SlowAPI)                                      │    │
│  │  • JWT OAuth2 Bearer auth                                       │    │
│  │  • Global exception handler → structured JSON envelopes         │    │
│  │  • CORS for localhost:3000                                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│  ┌─────────────┐  ┌─────────┴──────────┐  ┌─────────────────────────┐  │
│  │  Auth       │  │  Business Routers  │  │  Background Tasks       │  │
│  │  /auth      │  │  /products         │  │  Celery Workers         │  │
│  │             │  │  /listings         │  │  Celery Beat Scheduler  │  │
│  │             │  │  /orders           │  │                         │  │
│  │             │  │  /pricing/rules    │  │                         │  │
│  │             │  │  /sourcing         │  │                         │  │
│  │             │  │  /sync             │  │                         │  │
│  └─────────────┘  └────────────────────┘  └─────────────────────────┘  │
└─────────┬──────────────────────────┬────────────────────────────────────┘
          │                          │
┌─────────▼──────────┐    ┌──────────▼──────────┐
│   Data Layer       │    │   Message Queue     │
│   PostgreSQL 16    │    │   Redis 7           │
│   (async + sync)   │    │   • Celery broker   │
│   Alembic migrations│   │   • Result backend  │
└────────────────────┘    └─────────────────────┘
          ▲
          │
┌─────────┴───────────────────────────────────────────────────────────────┐
│                         External APIs                                    │
│  ┌─────────────────────────┐    ┌─────────────────────────────────────┐ │
│  │  Amazon PA-API v5       │    │  eBay REST API (OAuth 2.0 CC)       │ │
│  │  • AWS SigV4 auth       │    │  • Sell Inventory API               │ │
│  │  • SearchItems          │    │  • Sell Fulfillment API             │ │
│  │  • GetItems             │    │  • OAuth token refresh              │ │
│  │  • GetBrowseNodes       │    │  • Webhook ingestion                │ │
│  └─────────────────────────┘    └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Service Topology (Docker Compose)

| Service | Role | Image / Build |
|---------|------|---------------|
| `api` | FastAPI app server | `Dockerfile` multi-stage |
| `worker` | Celery task executor | `Dockerfile` multi-stage |
| `beat` | Celery beat scheduler | `Dockerfile` multi-stage |
| `db` | PostgreSQL 16 | `postgres:16-alpine` |
| `redis` | Broker + result backend | `redis:7-alpine` |

---

## 4. Data Model

### 4.1 Entity Relationship Overview

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Product   │◄──────│   Listing   │◄──────│    Order    │
│  (source)   │  1:N  │  (eBay)     │  1:N  │  (sale)     │
└──────┬──────┘       └─────────────┘       └─────────────┘
       │
       │ 1:N
┌──────▼──────┐
│PriceHistory │
└─────────────┘

┌─────────────┐       ┌─────────────┐
│PricingRule  │       │   SyncLog   │
│(strategy)   │       │ (audit)     │
└─────────────┘       └─────────────┘

┌─────────────┐
│    User     │
│   (auth)    │
└─────────────┘
```

### 4.2 Core Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `products` | Source catalog from Amazon | `asin` (unique), `title`, `brand`, `category`, `amazon_price`, `current_price`, `source` |
| `listings` | eBay draft/active listings | `product_id` (FK), `ebay_item_id`, `ebay_sku`, `listing_price`, `quantity`, `status` |
| `orders` | eBay sales + fulfillment | `listing_id` (FK), `ebay_order_id`, `sale_price`, `status`, `purchase_cost`, `profit`, `margin_percent` |
| `price_history` | Time-series price snapshots | `product_id` (FK), `price`, `currency`, `source`, `recorded_at` |
| `sync_log` | Background job audit trail | `sync_type`, `status`, `records_processed/succeeded/failed`, `started_at`, `completed_at` |
| `pricing_rules` | Reusable pricing strategies | `rule_type` (`fixed_markup` / `percentage` / `fixed_price`), `value`, `min/max_price`, `priority` |
| `users` | Local JWT authentication | `username` (unique), `email`, `hashed_password`, `is_active`, `is_superuser` |

### 4.3 Enumerations

- **ProductSource**: `amazon`
- **ListingStatus**: `draft`, `active`, `ended`, `sold`
- **OrderStatus**: `pending`, `shipped`, `delivered`, `cancelled`, `returned`
- **FulfillmentStatus**: `not_started`, `in_progress`, `delivered`
- **SyncType**: `amazon_product`, `ebay_listing`, `ebay_order`, `price_refresh`, `stock_sync`, `price_sync`
- **RuleType**: `fixed_markup`, `percentage`, `fixed_price`

---

## 5. API Design

### 5.1 RESTful Versioning
- Base path: `/api/v1`
- Content type: `application/json`
- Error envelope: `{"detail": "...", "status_code": NNN}`

### 5.2 Authentication
- **OAuth2 Password Bearer** (JWT `HS256`)
- Token endpoint: `POST /api/v1/auth/login`
- Default expiry: 30 minutes
- All business endpoints (except health and public order webhook) require `Authorization: Bearer <token>`.

### 5.3 Endpoint Groups

| Group | Prefix | Key Endpoints |
|-------|--------|---------------|
| Health | `/api/v1/health` | `GET /health` |
| Auth | `/api/v1/auth` | `POST /login`, `POST /register` |
| Products | `/api/v1/products` | `GET`, `POST`, `GET /{id}`, `GET /asin/{asin}` |
| Listings | `/api/v1/listings` | `GET`, `POST`, `GET /{id}`, `PATCH /{id}/status`, `POST /{id}/publish` |
| Orders | `/api/v1/orders` | `GET`, `POST`, `GET /{id}`, `PATCH /{id}/status`, `PATCH /{id}/fulfillment`, `POST /{id}/mark-purchased`, `POST /{id}/purchase-link` |
| Pricing | `/api/v1/pricing` | `GET /rules`, `POST /rules`, `PATCH /rules/{id}`, `DELETE /rules/{id}`, `POST /calculate` |
| Sourcing | `/api/v1/sourcing` | `POST /search` |
| Sync | `/api/v1/sync` | `POST /run/{sync_type}` (manual trigger) |
| Webhooks | `/api/v1/orders` | `POST /webhook` (public, eBay pushes) |

### 5.4 Request/Response Validation
- **Pydantic v2** schemas with `ConfigDict(from_attributes=True)` for ORM serialization.
- Field-level validators: URL scheme checks, positive price/quantity guards, min/max price consistency.
- Model-level validators: cross-field business rules (e.g., `min_price <= max_price`).

---

## 6. External Integrations

### 6.1 Amazon Product Advertising API v5

**Authentication:** AWS Signature Version 4 (SigV4)  
**Client:** `AmazonProductAPI` (`app/services/amazon_api.py`)

| Operation | PA-API Endpoint | Purpose |
|-----------|-----------------|---------|
| `search_items` | `POST /paapi5/searchitems` | Keyword or browse-node search for sourcing |
| `get_items` | `POST /paapi5/getitems` | Batch price/stock refresh by ASIN |
| `get_browse_nodes` | `POST /paapi5/getbrowsenodes` | Category tree navigation |

**Resilience:**
- Circuit breaker: `amazon_api` (failure threshold 5, recovery 60s).
- Retry: 3 attempts with exponential backoff (base 1s, max 60s, jitter).
- Retryable statuses: `429, 500, 502, 503, 504`.

**Constraints:**
- Max `ItemCount` per call: 10.
- Max `ItemIds` per `GetItems`: 10.
- Rate limits enforced by Amazon; client retries on `429`.

### 6.2 eBay REST API

**Authentication:** OAuth 2.0 Client Credentials flow  
**Client:** `EbayAPI` (`app/services/ebay_api.py`)

| Operation | eBay Endpoint | Purpose |
|-----------|---------------|---------|
| Token refresh | `POST /identity/v1/oauth2/token` | Scoped: `sell.inventory`, `sell.fulfillment` |
| Inventory CRUD | `/sell/inventory/v1/inventory_item/{sku}` | Create / update / delete item catalog |
| Offer CRUD | `/sell/inventory/v1/offer` | Pricing, quantity, category, duration |
| Publish / Withdraw | `/sell/inventory/v1/offer/{id}/publish` | Go live or end a listing |
| Orders | `/sell/fulfillment/v1/order` | Poll for sales |

**Resilience:**
- Circuit breaker: `ebay_api`.
- Retry: same config as Amazon.
- **Special handling:** `401` triggers an immediate in-band token refresh and single retry before falling back to exponential backoff.
- Offer lookups by SKU require client-side pagination (page size 200).

**Webhook:**
- `POST /api/v1/orders/webhook` accepts inbound eBay order events (public, no auth).
- Payload is validated via `OrderWebhookPayload` Pydantic schema and persisted as `Order` with `raw_payload` audit field.

---

## 7. Background Jobs & Scheduling

**Celery Configuration:**
- Broker & backend: Redis (configurable via `REDIS_URL`).
- Serializers: JSON only.
- Worker prefetch: `1` (acks late, fair distribution).
- Timezone: UTC.

### 7.1 Beat Schedule

| Task | Celery Task Name | Interval | Description |
|------|------------------|----------|-------------|
| Sync Amazon products | `tasks.sync_amazon_products` | 12 hours | Bulk catalog refresh |
| Sync eBay listings | `tasks.sync_ebay_listings` | 1 hour | Mirror active eBay offers |
| Sync eBay orders | `tasks.sync_ebay_orders` | 30 minutes | Poll fulfillment API |
| Refresh Amazon prices | `tasks.refresh_amazon_prices` | 2 hours | Update `current_price` + `price_history` |
| Sync Amazon stock | `tasks.sync_amazon_stock` | 6 hours | Update available quantities |
| Sync Amazon prices (duplicate alias) | `tasks.sync_amazon_prices` | 2 hours | Same as refresh (noted for cleanup) |

### 7.2 Task Modules

- `app/tasks/amazon_tasks.py` — PA-API fetch, search, price refresh.
- `app/tasks/ebay_tasks.py` — Listing sync, offer publish/withdraw.
- `app/tasks/order_sync.py` — Order polling and webhook processing.
- `app/tasks/price_sync.py` — Price delta detection and eBay offer updates.
- `app/tasks/stock_sync.py` — Stock delta detection and eBay inventory updates.
- `app/tasks/sourcing_tasks.py` — Automated sourcing pipelines.

---

## 8. Resilience Patterns

All external API calls are wrapped with a uniform resilience stack defined in `app/core/resilience.py`.

### 8.1 Circuit Breaker
- **States:** `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`.
- **Trigger:** 5 consecutive failures.
- **Recovery timeout:** 60 seconds.
- **Half-open probe limit:** 3 successful calls required to close.
- **Scope:** Per external API (Amazon, eBay) with in-memory state. For horizontal scaling, a Redis-backed breaker can be substituted later.

### 8.2 Retry with Exponential Backoff
- **Max retries:** 3.
- **Base delay:** 1 second.
- **Max delay:** 60 seconds.
- **Exponential base:** 2.
- **Jitter:** Up to 25% randomisation to prevent thundering herd.

### 8.3 Rate Limiting
- **SlowAPI** integration with `Limiter` stored in `app.state.limiter`.
- Default: `100/minute`.
- Auth endpoints: `10/minute`.
- Returns `429` with standard error envelope when exceeded.

---

## 9. Security Model

### 9.1 Authentication
- **OAuth2 Password Bearer** with JWT (`HS256`).
- Password hashing: `bcrypt` via PassLib.
- Token payload: `{"sub": "<username>", "exp": <timestamp>}`.
- No refresh token flow in v0.1.0; clients must re-login after expiry.

### 9.2 Authorization
- Two roles: `is_active` (required for all protected routes) and `is_superuser` (future extension).
- Dependency: `get_current_active_user` guards all business routers.

### 9.3 Transport & Headers
- CORS restricted to `ALLOWED_ORIGINS` (default: `localhost:3000`, `localhost:8000`).
- Credentials allowed; methods: `GET, POST, PATCH, DELETE, OPTIONS`.
- `X-Request-ID` accepted for tracing.

### 9.4 Secrets Management
- `SECRET_KEY`, `DATABASE_URL`, and API credentials have **no defaults** in `Settings` to prevent accidental deployment with hardcoded secrets.
- All secrets injected via `.env` file or environment variables.

### 9.5 Container Security
- Dockerfile runs as non-root `appuser` in the runtime stage.
- Build tools stripped in multi-stage build.
- Healthcheck endpoint exposed for orchestrator probes.

---

## 10. Frontend Architecture

### 10.1 Stack
- **Framework:** Next.js 16 (App Router)
- **Runtime:** React 19
- **Styling:** Tailwind CSS 4
- **Charts:** Recharts 3
- **Testing:** Jest 30 + React Testing Library + Playwright E2E

### 10.2 App Router Structure

| Route | Page Component | Purpose |
|-------|----------------|---------|
| `/` | `page.tsx` | Dashboard (KPIs, profit trend, margin distribution, recent orders) |
| `/products` | `products/page.tsx` | Product catalog browsing |
| `/listings` | `listings/page.tsx` | eBay listings management |
| `/listings/new` | `listings/new/page.tsx` | Create listing from product |
| `/orders` | `orders/page.tsx` | Order list |
| `/orders/[id]` | `orders/[id]/page.tsx` | Order detail + fulfillment |
| `/pricing` | `pricing/page.tsx` | Pricing rules CRUD |
| `/profits` | `profits/page.tsx` | Profit summaries and breakdowns |

### 10.3 API Client (`lib/api.ts`)
- Thin fetch wrapper with:
  - Automatic JSON parsing.
  - Exponential backoff retry for `5xx` / `429` / network errors.
  - AbortSignal support for request cancellation.
  - TypeScript interfaces mirroring backend Pydantic schemas.

### 10.4 Shared Components
- `Sidebar.tsx` — Navigation rail with active route highlighting.
- `KpiCard.tsx` — Metric card with optional subtext and href.
- `Skeleton.tsx` — Loading placeholder using Tailwind animate-pulse.

### 10.5 State Management
- No global state library (Redux/Zustand) in v0.1.0.
- Local component state via `useState` / `useEffect`.
- Data fetching co-located in page components for simplicity.

---

## 11. Deployment & Operations

### 11.1 Local Development
```bash
cp .env.example .env
docker compose up --build
```
- API with `--reload` for instant code changes.
- Worker and Beat auto-restarted via volume mounts.
- PostgreSQL and Redis with healthchecks.

### 11.2 Production
```bash
cp .env.example .env  # fill production values
docker compose -f docker-compose.prod.yml up -d --build
```

**Production hardening:**
- Strong `SECRET_KEY` (cryptographically random).
- Restrict `ALLOWED_ORIGINS` to actual frontend domain.
- Run migrations in an init container rather than on app startup (if scaling API horizontally).
- Place reverse proxy (Traefik / Nginx) in front for TLS termination.
- Resource limits and restart policies defined in `docker-compose.prod.yml`.

### 11.3 Database Migrations
- **Alembic** with async + sync engines.
- Autogenerate: `alembic revision --autogenerate -m "desc"`
- Apply: `alembic upgrade head`
- Entrypoint script (`scripts/entrypoint.sh`) runs migrations before starting Uvicorn.

### 11.4 Monitoring & Logging
- Structured logging via Python `logging` module.
- Celery task events tracked (`task_track_started=True`).
- Sync logs table provides human-readable job audit history.
- Health endpoint: `GET /api/v1/health` (used by Dockerfile `HEALTHCHECK`).

---

## 12. Testing Strategy

### 12.1 Backend
- **Framework:** pytest with async support.
- **Coverage:** `.coverage` artefact present; target ≥ 80%.
- **Test categories:**
  - Unit tests for services (mocked external APIs).
  - Schema validation tests (Pydantic edge cases).
  - API integration tests (TestClient with async DB session).

### 12.2 Frontend
- **Unit:** Jest + React Testing Library (`*.test.tsx`).
- **E2E:** Playwright (`e2e/*.spec.ts`).
- **Key flows covered:**
  - Critical user journeys (dashboard → products → listings → orders).
  - Error states (network failure, empty data).

---

## 13. Configuration Reference

All settings are managed via `pydantic-settings` (`app/core/config.py`) and sourced from `.env`.

| Category | Key Variables |
|----------|---------------|
| Database | `DATABASE_URL`, `DATABASE_URL_SYNC` |
| Redis | `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` |
| Security | `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `ALGORITHM` |
| Amazon | `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`, `AMAZON_PARTNER_TAG`, `AMAZON_HOST`, `AMAZON_REGION` |
| eBay | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_DEV_ID`, `EBAY_RU_NAME`, `EBAY_SITE_ID`, `EBAY_API_BASE_URL` |
| Sync Intervals | `STOCK_SYNC_INTERVAL` (21600s), `PRICE_SYNC_INTERVAL` (7200s) |
| Sourcing | `DEFAULT_PROFIT_MARGIN_THRESHOLD` (0.15), `DEFAULT_MAX_PRICE_USD` (200), `DEFAULT_MIN_PRICE_USD` (5) |
| Resilience | `CB_FAILURE_THRESHOLD` (5), `CB_RECOVERY_TIMEOUT_SECONDS` (60), `RETRY_MAX_RETRIES` (3) |

---

## 14. Future Considerations & Roadmap

### 14.1 Scalability
- **Redis-backed circuit breaker** for multi-replica deployments.
- **Read replicas** for PostgreSQL if analytics queries grow heavy.
- **Celery task routing** to dedicated queues (e.g., `ebay.high`, `amazon.low`).

### 14.2 Features
- **Multi-marketplace support:** eBay UK, DE, AU (site ID parameter already present).
- **Automated Amazon purchasing:** Integration with Amazon Business API or affiliate deep-linking.
- **Inventory buffers:** Safety stock thresholds to prevent overselling during sync delays.
- **Alerts & notifications:** Webhook or email alerts for margin drops, zero-stock events, or order anomalies.
- **Advanced pricing:** Time-based rules, competitor repricing hooks.

### 14.3 Observability
- **OpenTelemetry** tracing for request flows (API → Service → External API).
- **Prometheus metrics** for Celery task latency, circuit breaker state, and API rate-limit hits.
- **Structured JSON logging** aggregated to Loki / CloudWatch.

### 14.4 Frontend
- **React Query / SWR** for server-state caching and background refetching.
- **Server Components** migration for data-heavy pages to reduce client JS bundle.
- **Real-time updates:** WebSocket or SSE for order notifications.

---

## 15. Appendix: File Structure

```
.
├── app/
│   ├── api/v1/endpoints/      # FastAPI routers
│   ├── core/                  # Config, DB, security, limiter, resilience
│   ├── models/                # SQLAlchemy ORM
│   ├── schemas/               # Pydantic DTOs
│   ├── services/              # Business logic + external API clients
│   └── tasks/                 # Celery tasks & scheduler config
├── alembic/                   # Database migrations
├── dashboard/
│   ├── app/                   # Next.js App Router pages
│   ├── components/            # Shared UI components
│   ├── lib/                   # API client + types
│   └── e2e/                   # Playwright tests
├── scripts/
│   ├── entrypoint.sh          # Container entrypoint
│   └── run_migrations.sh
├── tests/                     # Pytest suite
├── Dockerfile                 # Multi-stage production image
├── docker-compose.yml         # Local dev stack
├── docker-compose.prod.yml    # Production stack
├── .env.example               # Environment variable template
└── README.md                  # Quick-start guide
```

---

*End of Document*
