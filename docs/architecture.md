# System Architecture

**Project:** Amazon-to-eBay Reselling Automation  
**Date:** 2026-05-11  
**Issue:** [CPRAA-107](/CPRAA/issues/CPRAA-107)

---

## 1. High-Level Architecture

The platform is a **three-tier application** with asynchronous background processing. It separates the public API surface, the operational dashboard, and the long-running sync jobs into distinct runtime units that share a single PostgreSQL database and Redis message broker.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Client Layer                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Next.js 16 Dashboard (React 19, Tailwind CSS, Recharts)        │    │
│  │  • JWT Bearer authentication                                    │    │
│  │  • Exponential-backoff fetch client                             │    │
│  │  • Dark mode + responsive layout                                │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ HTTPS / CORS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                   │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  FastAPI 0.1.0 (Python 3.13, Uvicorn)                           │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │    │
│  │  │  Auth       │  │  Business   │  │  Background Tasks       │  │    │
│  │  │  Router     │  │  Routers    │  │  (Celery)               │  │    │
│  │  │             │  │             │  │                         │  │    │
│  │  │  /auth      │  │  /products  │  │  • Price Sync Worker    │  │    │
│  │  │             │  │  /listings  │  │  • Stock Sync Worker    │  │    │
│  │  │  JWT/OAuth2 │  │  /orders    │  │  • Order Sync Worker    │  │    │
│  │  │  bcrypt     │  │  /pricing   │  │  • Sourcing Worker      │  │    │
│  │  │             │  │  /sourcing  │  │  • Beat Scheduler       │  │    │
│  │  │             │  │  /sync      │  │                         │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │    │
│  │                                                                  │    │
│  │  Cross-cutting: Rate limiting, CORS, global exception handler    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
            │  PostgreSQL  │ │    Redis     │ │  External    │
            │     16       │ │      7       │ │    APIs      │
            │              │ │              │ │              │
            │  • Products  │ │  • Celery    │ │  • Amazon    │
            │  • Listings  │ │    Broker    │ │    PA-API    │
            │  • Orders    │ │  • Celery    │ │  • eBay      │
            │  • Pricing   │ │    Backend   │ │    REST API  │
            │  • Users     │ │              │ │              │
            │  • Sync Log  │ │              │ │              │
            └──────────────┘ └──────────────┘ └──────────────┘
```

---

## 2. Component Breakdown

### 2.1 Dashboard (Next.js 16)

**Responsibilities:**
- Provide the reseller with a unified operational view.
- Authenticate against the FastAPI backend via JWT.
- Render analytics (profit trends, margin distribution, KPIs).
- Support CRUD for products, listings, orders, and pricing rules.

**Runtime:**
- Development: `next dev` on port `3000`.
- Production: `next build` → `next start` (or exported static + reverse proxy).

**Key Modules:**
- `app/page.tsx` — Dashboard home with Recharts visualisations.
- `app/products/page.tsx` — Product catalog.
- `app/listings/page.tsx` + `app/listings/new/page.tsx` — Listing management.
- `app/orders/page.tsx` + `app/orders/[id]/page.tsx` — Order tracking.
- `app/pricing/page.tsx` — Pricing rules CRUD.
- `app/profits/page.tsx` — Profit analytics.
- `lib/api.ts` — Typed fetch client with retry logic.
- `components/Sidebar.tsx`, `KpiCard.tsx`, `Skeleton.tsx` — Shared UI.

### 2.2 API Server (FastAPI)

**Responsibilities:**
- Expose a versioned REST API (`/api/v1`).
- Authenticate and authorise requests (JWT + active-user guard).
- Validate request/response payloads (Pydantic v2).
- Rate-limit endpoints to protect against abuse.
- Return structured error envelopes for all failure modes.

**Lifespan:**
- On startup: creates SQLAlchemy tables via `Base.metadata.create_all`.
- This is acceptable for single-node deployments; for multi-replica, use an init container.

**Router Organisation:**

| Router | Prefix | Auth | Notes |
|--------|--------|------|-------|
| `health` | `/api/v1/health` | Public | Liveness/readiness probe |
| `auth` | `/api/v1/auth` | Public | Login, register, token issuance |
| `products` | `/api/v1/products` | Protected | Catalog CRUD |
| `listings` | `/api/v1/listings` | Protected | eBay listing CRUD + publish |
| `orders` | `/api/v1/orders` | Protected | Order management |
| `orders_webhook` | `/api/v1/orders` | Public | eBay inbound webhook |
| `pricing` | `/api/v1/pricing` | Protected | Pricing rules + calculator |
| `sourcing` | `/api/v1/sourcing` | Protected | Amazon search + margin estimation |
| `sync` | `/api/v1/sync` | Protected | Manual sync triggers |

### 2.3 Background Workers (Celery)

**Responsibilities:**
- Execute time-consuming or periodic tasks outside the request path.
- Poll external APIs on a schedule.
- Update database state and sync logs atomically.

**Topology:**
- **Broker:** Redis (`CELERY_BROKER_URL`).
- **Backend:** Redis (`CELERY_RESULT_BACKEND`).
- **Worker process:** `celery -A app.tasks.celery_app worker --concurrency=2`.
- **Beat process:** `celery -A app.tasks.celery_app beat` (scheduler).

**Task Inventory:**

| Task | Module | Trigger | Purpose |
|------|--------|---------|---------|
| `sync_amazon_products` | `amazon_tasks` | Beat (12h) | Bulk refresh of catalog |
| `sync_ebay_listings` | `ebay_tasks` | Beat (1h) | Mirror eBay offer state |
| `sync_ebay_orders` | `order_sync` | Beat (30m) | Poll fulfillment API |
| `refresh_amazon_prices` | `price_sync` | Beat (2h) | Detect price changes |
| `sync_amazon_stock` | `stock_sync` | Beat (6h) | Detect stock changes |
| `sync_amazon_prices` | `price_sync` | Beat (2h) | Alias (cleanup needed) |

### 2.4 Database (PostgreSQL 16)

**Responsibilities:**
- Persistent storage for all domain entities.
- ACID guarantees for order and financial data.
- Async I/O via `asyncpg` (SQLAlchemy async engine).

**Access Patterns:**
- API server: async sessions (`AsyncSession`, `expire_on_commit=False`).
- Alembic migrations: sync sessions (`DATABASE_URL_SYNC`).

**Indexes:**
- `products.asin` (unique).
- `listings.status + product_id` (compound).
- `orders.status + ebay_order_id` (compound).
- `price_history.product_id + recorded_at` (compound, time-series queries).
- `pricing_rules.is_active + priority` (compound, rule selection).

### 2.5 Message Broker (Redis 7)

**Responsibilities:**
- Celery task queue and result store.
- Optional future use: distributed circuit breaker state, caching, session store.

**Configuration:**
- Built from components (`REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`).
- Password optional; defaults to no auth for local dev.

---

## 3. Data Flow

### 3.1 Sourcing Flow

```
User searches keywords in Dashboard
         │
         ▼
Dashboard POST /api/v1/sourcing/search
         │
         ▼
FastAPI ──► SourcingService ──► AmazonProductAPI.search_items()
         │                           │
         │                           ▼
         │                    Amazon PA-API v5
         │                           │
         │                           ▼
         │                    Results + margin estimate
         │                           │
         ▼                           ▼
    Response: SourcingResult[]
         │
         ▼
    User selects product → auto-create listing (optional)
```

### 3.2 Listing Creation Flow

```
User creates listing from product
         │
         ▼
Dashboard POST /api/v1/listings
         │
         ▼
FastAPI ──► ListingService ──► EbayAPI.create_listing()
         │                         │
         │                         ▼
         │              1. PUT inventory_item/{sku}
         │              2. POST offer
         │              3. POST offer/{id}/publish
         │                         │
         │                         ▼
         │                    eBay Inventory API
         │                         │
         │                         ▼
         │              Response: {sku, offer_id, item_id, status}
         │                         │
         ▼                         ▼
    DB: Listing row created with status = active
```

### 3.3 Order Ingestion Flow

```
         ┌──────────────────────────────────────────┐
         │  eBay platform generates sale            │
         └──────────────┬───────────────────────────┘
                        │
         ┌──────────────▼───────────────────────────┐
         │  Option A: Webhook POST                  │
         │  /api/v1/orders/webhook                  │
         └──────────────┬───────────────────────────┘
                        │
         ┌──────────────▼───────────────────────────┐
         │  Option B: Celery Beat polls             │
         │  sync_ebay_orders every 30m              │
         └──────────────┬───────────────────────────┘
                        │
                        ▼
              FastAPI OrderService
                        │
                        ▼
              DB: Order row inserted
                        │
                        ▼
              Dashboard shows new order
                        │
                        ▼
              User marks purchased, enters cost
                        │
                        ▼
              DB: profit & margin_percent computed
```

### 3.4 Price Sync Flow

```
Celery Beat triggers refresh_amazon_prices
         │
         ▼
PriceSyncTask ──► AmazonProductAPI.get_items(asins)
         │              │
         │              ▼
         │       Amazon PA-API v5
         │              │
         │              ▼
         │       New prices returned
         │              │
         ▼              ▼
    DB: product.current_price updated
    DB: price_history snapshot inserted
         │
         ▼
    If delta >= PRICE_SYNC_MIN_DELTA_PERCENT
         │
         ▼
    EbayAPI.update_listing(sku, price)
         │
         ▼
    eBay offer price updated
```

---

## 4. External API Integration Architecture

### 4.1 Amazon Product Advertising API v5

**Auth:** AWS Signature Version 4 (SigV4)  
**Client:** `AmazonProductAPI` (`app/services/amazon_api.py`)

- `access_key`, `secret_key`, `partner_tag` required.
- Requests signed with `AWS4-HMAC-SHA256`.
- `httpx.AsyncClient` with 30s timeout.
- All calls wrapped with circuit breaker + retry.

**Endpoints Used:**
- `SearchItems` — keyword/category search.
- `GetItems` — batch lookup by ASIN (max 10 per call).
- `GetBrowseNodes` — category tree navigation.

**Data Mapping:**
- `ASIN` → `Product.asin`
- `ItemInfo.Title.DisplayValue` → `Product.title`
- `Offers.Listings[0].Price.Amount` → `Product.amazon_price`
- `Images.Primary.Large.URL` → `Product.image_url`

### 4.2 eBay REST API

**Auth:** OAuth 2.0 Client Credentials (`client_id` + `client_secret`)  
**Client:** `EbayAPI` (`app/services/ebay_api.py`)

- Token refreshed automatically on expiry or `401`.
- Scope: `sell.inventory`, `sell.fulfillment`.
- Marketplace ID resolved from `EBAY_SITE_ID` (default `EBAY_US`).

**Endpoints Used:**
- `PUT /sell/inventory/v1/inventory_item/{sku}` — catalog data.
- `POST /sell/inventory/v1/offer` — pricing/quantity offer.
- `POST /sell/inventory/v1/offer/{id}/publish` — go live.
- `POST /sell/inventory/v1/offer/{id}/withdraw` — end listing.
- `GET /sell/fulfillment/v1/order` — order polling.

**Data Mapping:**
- `sku` = `Listing.ebay_item_id` (treated as SKU in v0.1.0).
- `offerId` → `Listing.ebay_item_id` (after publish, `listingId` used).

---

## 5. Resilience Architecture

All external API interactions pass through a uniform resilience layer (`app/core/resilience.py`).

```
Caller
  │
  ▼
CircuitBreaker.can_execute?
  │ Yes
  ▼
with_retry(func, config, breaker)
  │
  ├──► Attempt 1
  │      │
  │      ├──► Success ──► breaker.record_success() ──► return
  │      │
  │      └──► Retryable? ──► backoff sleep ──► Attempt 2 ...
  │
  └──► Exhausted ──► breaker.record_failure() ──► raise
```

**Per-API Configuration:**

| Parameter | Amazon | eBay |
|-----------|--------|------|
| Failure threshold | 5 | 5 |
| Recovery timeout | 60s | 60s |
| Max retries | 3 | 3 |
| Base delay | 1s | 1s |
| Max delay | 60s | 60s |

**Special Cases:**
- eBay `401`: immediate in-band token refresh + single retry before backoff.
- Non-retryable errors (`400`, `403`, `404`, `422`): fail fast, record failure.

---

## 6. Security Architecture

```
Client ──► [HTTPS] ──► Reverse Proxy (TLS termination)
                         │
                         ▼
                    FastAPI Server
                         │
                    ┌────┴────┐
                    │  CORS   │ ──► origin whitelist
                    │  Limiter│ ──► rate limits
                    │  OAuth2 │ ──► JWT validation
                    └────┬────┘
                         │
                    ┌────┴────┐
                    │ bcrypt  │ ──► password hashing
                    │ jose/jwt│ ──► token encode/decode
                    └─────────┘
```

- **Transport:** HTTPS in production; CORS restricted to known origins.
- **Auth:** Stateless JWT (Bearer); no server-side session store.
- **Secrets:** No defaults in code; loaded from `.env` at runtime.
- **Container:** Non-root user (`appuser`) in runtime stage.

---

## 7. Deployment Architecture

### 7.1 Local Development

```
docker compose up --build
```

- `api`: Uvicorn with `--reload`.
- `worker` + `beat`: Celery with live code mounts.
- `db` + `redis`: Persistent volumes.

### 7.2 Production

```
docker compose -f docker-compose.prod.yml up -d --build
```

- Resource limits and restart policies.
- Healthchecks on all services.
- Migrations recommended in init container (not app startup) for horizontal scaling.
- Reverse proxy (Traefik / Nginx) for TLS and load balancing.

### 7.3 Scaling Vectors

| Bottleneck | Mitigation |
|------------|------------|
| API CPU | Horizontal replica scaling behind load balancer |
| DB reads | Read replicas for analytics queries |
| Celery queue depth | Add worker replicas; route to dedicated queues |
| External API rate limits | Backoff + jitter; circuit breaker prevents hammering |

---

*End of Document*
