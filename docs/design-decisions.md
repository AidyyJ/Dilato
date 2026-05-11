# Design Decisions

This document records the significant architectural and implementation decisions made during the design of the Amazon-to-eBay Reseller platform, along with the rationale and trade-offs for each.

---

## 1. Async-First Backend (FastAPI + async SQLAlchemy)

**Decision:** Use FastAPI with `asyncpg` and SQLAlchemy 2.x async ORM.

**Rationale:**
- The workload is I/O-bound: most request time is spent waiting on Amazon/eBay API responses and database queries.
- Async allows a single worker process to handle many concurrent requests without blocking.
- FastAPI's native `async`/`await` support and automatic OpenAPI generation reduce boilerplate.

**Trade-offs:**
- Alembic migrations require a synchronous connection (`DATABASE_URL_SYNC`), so we maintain two connection strings.
- Some third-party libraries may not support async; we wrap sync clients in `asyncio.to_thread` where needed.

---

## 2. Celery + Redis for Background Tasks

**Decision:** Use Celery with Redis as both broker and result backend for all background work.

**Rationale:**
- Price/stock sync, order polling, and listing updates must happen reliably outside the request/response cycle.
- Celery Beat provides a simple, battle-tested scheduler.
- Redis is lightweight and already required for caching/session potential.

**Trade-offs:**
- Adds operational complexity (worker monitoring, dead-letter handling).
- Redis is not a persistent queue by default; we accept the risk of losing in-flight tasks on Redis restart (mitigated by `task_acks_late=True`).

---

## 3. Decimal for All Monetary Values

**Decision:** Store and compute prices, fees, and margins using Python `Decimal` and SQLAlchemy `Numeric(10, 2)`.

**Rationale:**
- Floating-point arithmetic introduces rounding errors that compound in financial calculations.
- `Decimal` guarantees exact representation for base-10 currencies.

**Trade-offs:**
- Slightly more verbose code (explicit `Decimal(str(x))` conversions).
- JSON serialization requires custom encoders for Celery and API responses.

---

## 4. Circuit Breaker + Exponential Backoff for External APIs

**Decision:** Implement circuit breaker and retry logic in `app.core.resilience`.

**Rationale:**
- Amazon PA-API and eBay REST API have rate limits and occasional outages.
- A circuit breaker prevents cascading failures and reduces unnecessary API calls during outages.
- Exponential backoff with jitter respects provider rate limits.

**Configuration:**
- `CB_FAILURE_THRESHOLD=5`
- `CB_RECOVERY_TIMEOUT_SECONDS=60`
- `RETRY_MAX_RETRIES=3`
- `RETRY_BASE_DELAY_SECONDS=1.0`

**Trade-offs:**
- Adds complexity to API client code.
- Requires careful tuning of thresholds per external provider.

---

## 5. Pydantic Settings for Configuration

**Decision:** Use `pydantic-settings` (`BaseSettings`) to load all configuration from environment variables.

**Rationale:**
- Enforces type safety and validation at startup.
- No defaults for secrets (`SECRET_KEY`, database URLs) prevents accidental insecure deployments.
- Supports `.env` files for local development while keeping production strictly environment-driven.

**Trade-offs:**
- Startup fails fast if a required variable is missing (desired behavior for production, but can surprise new developers).

---

## 6. Soft Deletes for Pricing Rules

**Decision:** Deactivate pricing rules (`is_active=False`) instead of hard-deleting them.

**Rationale:**
- Pricing history and margin calculations may reference rules implicitly.
- Soft deletes allow easy restoration and audit without foreign-key cascades.

**Trade-offs:**
- Queries must always filter `is_active=True`.
- Table grows over time; a periodic cleanup job may be needed in the future.

---

## 7. Separate Sync Log Table

**Decision:** Maintain a dedicated `sync_log` table for all background sync operations rather than relying solely on worker logs.

**Rationale:**
- Provides a queryable, persistent audit trail of sync health.
- Enables the dashboard to show sync status and failure counts without parsing logs.

**Trade-offs:**
- Extra write overhead on every sync run.
- Requires periodic pruning to prevent unbounded growth.

---

## 8. JWT-Based Authentication

**Decision:** Use stateless JWT tokens for API authentication.

**Rationale:**
- Simple to implement with FastAPI dependencies.
- Scales horizontally without shared session storage.

**Trade-offs:**
- No built-in token revocation; changing a password does not invalidate existing tokens until expiry.
- Token refresh and rotation are not yet implemented (future enhancement).

---

## 9. Rate Limiting with Slowapi

**Decision:** Apply per-endpoint rate limits using `Slowapi` (in-memory storage, per-process).

**Rationale:**
- Protects against accidental abuse and brute-force attacks on auth endpoints.
- Default `100/minute` for general endpoints, `10/minute` for auth endpoints.

**Trade-offs:**
- In-memory storage means limits are per-process; behind a load balancer with multiple replicas, the effective limit is multiplied.
- Future upgrade: switch to Redis-backed storage for distributed rate limiting.

---

## 10. Docker Multi-Stage Build

**Decision:** Use a multi-stage Dockerfile with a non-root runtime user.

**Rationale:**
- Builder stage compiles Python extensions (`libpq-dev`) without bloating the runtime image.
- Non-root user (`appuser`) follows container security best practices.
- Healthcheck ensures orchestrators can detect and restart unhealthy containers.

**Trade-offs:**
- Slightly longer initial build time due to two stages.

---

## 11. Next.js Dashboard (Separate Service)

**Decision:** Keep the dashboard as a separate Next.js application rather than serving it from FastAPI.

**Rationale:**
- Decouples frontend and backend release cycles.
- Next.js provides SSR, static optimization, and a rich React ecosystem.
- The backend can be consumed by other clients (mobile apps, CLI tools) in the future.

**Trade-offs:**
- Requires CORS configuration.
- Two separate build pipelines and deployment artifacts.

---

## 12. Monolithic Repository

**Decision:** Maintain backend and dashboard in a single Git repository.

**Rationale:**
- Simplifies coordination for a small team.
- Shared Docker Compose files make local development consistent.
- Atomic commits that span backend + frontend changes are possible.

**Trade-offs:**
- Repository may grow large over time.
- CI/CD pipelines must be configured to only build changed services.

---

## Future Considerations

| Topic | Current State | Potential Evolution |
|-------|--------------|---------------------|
| **Auth** | JWT only | Add OAuth 2.0 / SSO, token refresh, revoke endpoint |
| **Rate Limiting** | In-memory | Redis-backed distributed limits |
| **Queue** | Redis | Evaluate RabbitMQ or SQS for persistence guarantees |
| **Frontend** | Next.js SPA | Consider SSR for SEO if public pages are added |
| **Observability** | Basic logging | Add OpenTelemetry tracing, Prometheus metrics |
| **Testing** | Pytest + Playwright | Increase unit-test coverage for services; add contract tests for external APIs |
