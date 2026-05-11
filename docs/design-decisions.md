# Key Technical Decisions & Rationale

**Project:** Amazon-to-eBay Reselling Automation  
**Date:** 2026-05-11  
**Issue:** [CPRAA-107](/CPRAA/issues/CPRAA-107)

---

## 1. Backend Framework: FastAPI + Python 3.13

**Decision:** Use FastAPI with Python 3.13 for the API server.

**Rationale:**
- **Async-native:** FastAPI is built on Starlette and supports `async/await` end-to-end, which is essential for I/O-bound workloads like calling external APIs (Amazon, eBay) and querying PostgreSQL asynchronously.
- **Type safety:** Pydantic v2 integration provides automatic request/response validation, serialisation, and OpenAPI documentation generation (Swagger UI / ReDoc).
- **Ecosystem maturity:** Rich ecosystem for SQLAlchemy 2.0, Celery, JWT, and testing.
- **Alternative considered:** Django + DRF — rejected because it is synchronous by default and heavier than needed for a JSON API backend.

**Trade-offs:**
- Less opinionated than Django; project structure and auth must be built manually.
- Smaller built-in admin ecosystem; the dashboard is a separate Next.js app.

---

## 2. Database: PostgreSQL 16 with SQLAlchemy 2.0

**Decision:** Use PostgreSQL 16 as the primary database, accessed via SQLAlchemy 2.0 async ORM.

**Rationale:**
- **ACID compliance:** Critical for financial data (orders, profit calculations).
- **Async support:** SQLAlchemy 2.0 + `asyncpg` driver allows non-blocking database operations, matching FastAPI's async model.
- **Alembic migrations:** Battle-tested migration framework with autogeneration support.
- **JSONB & indexing:** PostgreSQL supports advanced indexing strategies (compound indexes, partial indexes) that serve the query patterns of this app well.

**Trade-offs:**
- Requires two connection strings (`DATABASE_URL` for async, `DATABASE_URL_SYNC` for Alembic).
- Async ORM has a steeper learning curve than sync SQLAlchemy 1.x.

**Alternative considered:** SQLite — rejected because it lacks concurrent write support and is unsuitable for Celery workers + API server hitting the same DB.

---

## 3. Frontend: Next.js 16 App Router + React 19

**Decision:** Use Next.js 16 with the App Router, React 19, and Tailwind CSS 4.

**Rationale:**
- **App Router:** Enables React Server Components, nested layouts, and simpler data fetching patterns compared to the legacy Pages Router.
- **React 19:** Latest stable release with improved concurrency and hooks.
- **Tailwind CSS 4:** Utility-first styling enables rapid UI iteration and consistent design tokens without maintaining a large CSS codebase.
- **Recharts:** Mature, declarative charting library for profit analytics and KPI dashboards.

**Trade-offs:**
- Next.js 16 has breaking changes from earlier versions; team must refer to internal docs (`node_modules/next/dist/docs/`) rather than external training data.
- App Router caching semantics can be surprising; explicit `revalidate` or dynamic route configs may be needed later.

**Alternative considered:** Plain React SPA with Vite — rejected because SSR/SSG benefits (SEO, initial load, layout conventions) outweigh the added framework complexity for a dashboard app.

---

## 4. Background Jobs: Celery + Redis

**Decision:** Use Celery with Redis as both broker and result backend.

**Rationale:**
- **Mature task queue:** Celery is the de-facto standard for Python background processing. Supports periodic tasks (beat), retries, acks-late, and task routing.
- **Redis simplicity:** Single infrastructure component serves as broker, result store, and potential future cache. Low operational overhead.
- **Scheduling:** Built-in beat scheduler handles all recurring sync tasks without external cron.

**Trade-offs:**
- Redis does not guarantee message durability by default (AOF/RDB can be enabled).
- Celery has a larger memory footprint than lighter alternatives (e.g., `arq`).

**Alternative considered:** `arq` (async Redis queue) — rejected because Celery's ecosystem (beat, monitoring, Django-style task discovery) is richer and more familiar to Python backend engineers.

---

## 5. External API Resilience: Custom Circuit Breaker + Retry

**Decision:** Implement a custom async circuit breaker and retry layer (`app/core/resilience.py`) rather than using an off-the-shelf library like `pybreaker` or `tenacity`.

**Rationale:**
- **Unified semantics:** One consistent interface (`with_retry`) wraps both Amazon and eBay calls with the same backoff, jitter, and circuit breaker logic.
- **Special handling:** eBay requires custom `401` retry logic (token refresh) that generic libraries do not support out-of-the-box.
- **Async safety:** Many existing Python resilience libraries are sync-first or have awkward async APIs.
- **Observability:** Built-in logging at each retry attempt and circuit state transition.

**Trade-offs:**
- Maintenance burden of custom code versus community-tested library.
- In-memory circuit breaker state is not shared across API replicas (acceptable for v0.1.0; Redis-backed breaker can be added later).

---

## 6. Authentication: JWT (HS256) with OAuth2 Password Bearer

**Decision:** Use stateless JWT signed with `HS256` and the OAuth2 Password Bearer flow.

**Rationale:**
- **Stateless:** No server-side session store required; API server remains horizontally scalable without sticky sessions.
- **FastAPI native:** `fastapi.security.OAuth2PasswordBearer` integrates directly with OpenAPI docs, providing a built-in "Authorize" button in Swagger UI.
- **Simple rollout:** Single `SECRET_KEY` environment variable; no external identity provider needed for a single-reseller deployment.

**Trade-offs:**
- No built-in token revocation (logout is client-side only). For v0.1.0 with a single user, this is acceptable.
- `HS256` requires all services to share the same secret (fine for monolith; would switch to `RS256` if auth service were separate).
- Refresh tokens not implemented in v0.1.0; users must re-login after 30 minutes.

**Alternative considered:** Session cookies with Redis store — rejected because it adds infrastructure complexity (sticky sessions or shared session store) for minimal gain in a single-user context.

---

## 7. Container Strategy: Docker Multi-Stage Build

**Decision:** Use a multi-stage Dockerfile with a `builder` stage (compile deps) and a runtime stage (non-root user, minimal packages).

**Rationale:**
- **Image size:** Build tools (`build-essential`, `libpq-dev`) are stripped from the final image.
- **Security:** Runtime stage runs as `appuser` (non-root) and includes only `libpq5` and `curl`.
- **Healthcheck:** Built-in `HEALTHCHECK`指令 ensures orchestrators can detect unhealthy containers.

**Trade-offs:**
- Slightly longer build times due to two stages.
- Volume mounts in dev override the copied code, so the non-root user must have correct file permissions on the host.

---

## 8. Pricing Model: Rule-Based Engine

**Decision:** Implement a rule-based pricing engine (`PricingRule` table) with priority ordering rather than a hardcoded formula.

**Rationale:**
- **Flexibility:** Resellers can define fixed markup, percentage markup, or fixed price strategies without code changes.
- **Guardrails:** Each rule supports `min_price`, `max_price`, and `min_margin_percent` to prevent accidental loss-making listings.
- **Extensibility:** Future rule types (competitor-based, time-based) can be added by extending the `RuleType` enum and calculator logic.

**Trade-offs:**
- Slightly more complex than a single global margin setting.
- Rule priority resolution must be deterministic and well-documented.

---

## 9. Order Fulfillment: Manual Purchase Tracking

**Decision:** Track Amazon purchase costs manually (user enters `purchase_cost` and `amazon_order_id`) rather than automating Amazon checkout.

**Rationale:**
- **Legal/ToS:** Automated purchasing on Amazon violates their Terms of Service and can result in account bans.
- **Safety:** Manual verification ensures the reseller reviews the Amazon listing (condition, seller rating, shipping) before committing capital.
- **Simplicity:** No need for Amazon Business API credentials or bot-like automation.

**Trade-offs:**
- Higher operational overhead per order.
- Potential for human error in cost entry.

**Future path:** Deep-link generation (affiliate or one-click cart URLs) can reduce friction without violating ToS.

---

## 10. Monorepo vs. Polyrepo

**Decision:** Keep backend and frontend in a single monorepo with a shared Docker Compose setup.

**Rationale:**
- **Coordination:** API contracts (Pydantic schemas ↔ TypeScript interfaces) can be reviewed in the same PR.
- **DevEx:** One `docker compose up` starts the entire stack.
- **CI simplicity:** Single pipeline can run backend tests, frontend tests, and E2E tests against the same commit.

**Trade-offs:**
- Larger repository; `node_modules` and `.next` bloat the working tree.
- Independent deployment of frontend and backend is still possible (separate Docker images), but version coupling is tighter.

**Alternative considered:** Separate repos — rejected because the team size is small and cross-cutting changes are frequent.

---

## 11. Sync Strategy: Polling + Webhooks

**Decision:** Use Celery beat polling for most sync tasks, with an optional eBay order webhook for near-real-time order ingestion.

**Rationale:**
- **Amazon PA-API:** Does not support webhooks; polling is the only option.
- **eBay:** Supports webhooks, but webhook reliability (delivery guarantees, retry logic) varies. Polling acts as a safety net.
- **Simplicity:** A single beat schedule is easier to reason about and monitor than a hybrid webhook + polling system for every data type.

**Trade-offs:**
- Data freshness is bound by the polling interval (e.g., 30 minutes for orders).
- Polling consumes API rate limits even when nothing has changed.

**Future path:** Move to event-driven webhooks for eBay orders and listings once delivery guarantees are validated.

---

## 12. Decimal Handling for Currency

**Decision:** Use `decimal.Decimal` (mapped to `NUMERIC` in PostgreSQL) for all monetary fields rather than `float`.

**Rationale:**
- **Precision:** Floating-point arithmetic causes rounding errors that are unacceptable for financial calculations (profit, margin, fees).
- **Pydantic support:** Pydantic v2 serialises `Decimal` correctly to JSON strings.
- **Frontend parity:** Dashboard displays strings and converts to `Number` only for charting, preserving precision.

**Trade-offs:**
- Slightly more verbose than `float`.
- JSON serialisation requires explicit `Decimal` → `str` handling in some contexts.

---

*End of Document*
