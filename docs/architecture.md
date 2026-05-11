# System Architecture

This document describes the high-level architecture of the Amazon-to-eBay Reseller platform.

## Overview

The platform is a full-stack application composed of:
- a **Python/FastAPI** backend with async PostgreSQL and Celery workers,
- a **Next.js** dashboard frontend,
- **Docker** containers for local development and production deployment,
- external integrations with **Amazon Product Advertising API** and **eBay REST API**.

The architecture follows a **layered, service-oriented** design with clear separation between API routes, business logic, data access, and background task processing.

---

## High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Client Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐ │
│  │  Next.js    │  │  Swagger UI │  │  eBay Webhooks (push)       │ │
│  │  Dashboard  │  │  / Redoc    │  │  (order notifications)      │ │
│  │  (Port 3000)│  │  (Port 8000)│  │                             │ │
│  └──────┬──────┘  └─────────────┘  └─────────────────────────────┘ │
└─────────┼───────────────────────────────────────────────────────────┘
          │ HTTP / REST
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        API Gateway Layer                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Application (Port 8000)                             │   │
│  │  • CORS middleware (configurable origins)                    │   │
│  │  • Rate limiting (`Slowapi` — default 100/min, auth 10/min)  │   │
│  │  • JWT authentication (`/api/v1/auth/*`)                    │   │
│  │  • Health check (`/api/v1/health`)                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Service Layer                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────┐  │
│  │  Sourcing   │ │   Pricing   │ │  eBay API   │ │  Amazon API  │  │
│  │  Service    │ │   Service   │ │  Client     │ │  Client      │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────────┘  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────┐  │
│  │   Listing   │ │   Product   │ │   Order     │ │   Profit     │  │
│  │  Service    │ │   Service   │ │  Service    │ │  Service     │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────────┘  │
│  ┌─────────────┐ ┌─────────────┐                                    │
│  │   Listing   │ │  Purchase   │                                    │
│  │   Creator   │ │  Service    │                                    │
│  └─────────────┘ └─────────────┘                                    │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Data Layer                                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  PostgreSQL 16 (async via asyncpg / sync via psycopg2)       │   │
│  │  • SQLAlchemy 2.x ORM (declarative base)                     │   │
│  │  • Alembic migrations                                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Redis 7                                                     │   │
│  │  • Celery broker (task queue)                                │   │
│  │  • Celery result backend                                     │   │
│  │  • Optional: caching / session store                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Background Worker Layer                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Celery Workers (auto-scaled)                                │   │
│  │  • Amazon product sync                                       │   │
│  │  • eBay listing sync                                         │   │
│  │  • Price sync                                                │   │
│  │  • Stock sync                                                │   │
│  │  • Order sync                                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Celery Beat Scheduler                                       │   │
│  │  • Drives periodic tasks (intervals defined in config)       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     External APIs                                   │
│  ┌────────────────────────┐  ┌──────────────────────────────────┐  │
│  │  Amazon PA-API         │  │  eBay REST API (OAuth 2.0)       │  │
│  │  (product search,      │  │  • Inventory / Trading /         │  │
│  │   item lookup,         │  │    Sell APIs                     │  │
│  │   price & stock)       │  │  • Webhook push for orders       │  │
│  └────────────────────────┘  └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. FastAPI Application (`app/`)

| Directory | Purpose |
|-----------|---------|
| `app/api/v1/endpoints/` | REST route handlers (sourcing, listings, orders, products, pricing, sync, auth, health) |
| `app/core/` | Shared infrastructure: config (`pydantic-settings`), database engine, security (JWT), rate limiter, circuit breaker |
| `app/models/` | SQLAlchemy ORM models (`Product`, `Listing`, `Order`, `PriceHistory`, `SyncLog`, `PricingRule`, `User`) |
| `app/schemas/` | Pydantic request/response models and validation |
| `app/services/` | Business logic: API clients for Amazon/eBay, pricing engine, listing creator, order processing |
| `app/tasks/` | Celery task definitions and the Celery application factory |

### 2. Next.js Dashboard (`dashboard/`)

- Bootstrapped with `create-next-app`.
- Communicates with the backend via the REST API.
- Intended for listing management, sourcing configuration, pricing rule editing, and order tracking.
- End-to-end tests written with Playwright (`e2e/`).

### 3. Database (`PostgreSQL`)

| Table | Purpose |
|-------|---------|
| `products` | Amazon-sourced products with current price and metadata |
| `listings` | eBay draft/active/ended listings linked to products |
| `orders` | eBay orders with fulfillment and profit tracking |
| `price_history` | Time-series price records for audit and delta detection |
| `sync_log` | Audit log for all background sync operations |
| `pricing_rules` | Configurable markup rules with priority and constraints |
| `users` | Local admin/users for dashboard authentication |

### 4. Message Queue & Workers (`Redis` + `Celery`)

- **Broker:** Redis (configurable host/port/password).
- **Result backend:** Redis.
- **Workers:** Separate `worker` service in Docker Compose.
- **Scheduler:** Separate `beat` service driving periodic tasks.

### 5. External Integrations

| API | Purpose | Auth |
|-----|---------|------|
| Amazon PA-API | Search products, fetch prices/stock, get images | AWS Signature V4 (`AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`) |
| eBay REST API | Create/revise listings, sync orders, manage inventory | OAuth 2.0 client credentials (`EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`) |

---

## Request Flow Example (Sourcing)

1. **User** sends `POST /api/v1/sourcing/search` with keywords and filters.
2. **FastAPI** validates the request (Pydantic schema) and rate-limits the caller.
3. **Sourcing Service** calls the **Amazon API Client** to search PA-API.
4. For each result, the **Pricing Service** estimates eBay price and margin.
5. Promising products are persisted via **Product Service**.
6. If `auto_create_listings=True`, the **Listing Creator** generates draft listings.
7. Results are returned to the user; listings can later be published via the eBay API.

---

## Deployment Architecture

### Local Development

```bash
docker compose up --build
```

Services: `api` (FastAPI + auto-reload), `worker`, `beat`, `db`, `redis`.

### Production

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

- Multi-stage Dockerfile with a non-root `appuser`.
- Healthchecks on the API container.
- Resource limits and restart policies.
- Migrations run via `scripts/entrypoint.sh` on container start.
- Recommended: reverse proxy (Traefik/Nginx) for TLS termination.

See `deployment.md` for detailed environment and security guidance.
