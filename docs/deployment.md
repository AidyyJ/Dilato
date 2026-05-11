# Deployment Guide

This document describes how to build, configure, and deploy the Amazon-to-eBay Reseller platform in both local development and production environments.

---

## Prerequisites

- Docker 24+
- Docker Compose v2+
- (Optional) Python 3.13+ for local test/lint execution

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all required values.

### Required Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Async PostgreSQL connection string (e.g., `postgresql+asyncpg://postgres:postgres@db:5432/reseller`) |
| `DATABASE_URL_SYNC` | Sync PostgreSQL connection string for Alembic |
| `SECRET_KEY` | Cryptographically secure random string for JWT signing |

### Amazon PA-API Credentials

| Variable | Description |
|----------|-------------|
| `AMAZON_ACCESS_KEY` | AWS access key for Product Advertising API |
| `AMAZON_SECRET_KEY` | AWS secret key |
| `AMAZON_PARTNER_TAG` | Amazon associate tag |

### eBay REST API Credentials

| Variable | Description |
|----------|-------------|
| `EBAY_CLIENT_ID` | eBay developer program client ID |
| `EBAY_CLIENT_SECRET` | eBay developer program client secret |
| `EBAY_DEV_ID` | eBay developer ID |
| `EBAY_RU_NAME` | eBay RuName (OAuth redirect name) |

### Optional Overrides

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | built from components | Override full Redis connection string |
| `CELERY_BROKER_URL` | built from components | Override Celery broker URL |
| `CELERY_RESULT_BACKEND` | built from components | Override Celery result backend |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:8000` | CORS origins (comma-separated) |

---

## Local Development

### 1. Build and Start

```bash
cp .env.example .env
# Edit .env with your credentials
docker compose up --build
```

Services started:

| Service | Description | Exposed Port |
|---------|-------------|--------------|
| `api` | FastAPI application with auto-reload | `8000` |
| `worker` | Celery worker | — |
| `beat` | Celery Beat scheduler | — |
| `db` | PostgreSQL 16 | `5432` |
| `redis` | Redis 7 (broker + backend) | `6379` |

### 2. Interactive API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 3. Run Migrations Manually

```bash
docker compose exec api alembic upgrade head
```

### 4. Run Tests

```bash
# Inside the API container
docker compose exec api pytest

# Or locally with a virtual environment
pytest
```

### 5. Inspect Workers

```bash
docker compose logs -f worker
docker compose logs -f beat
docker compose exec worker celery -A app.tasks.celery_app inspect ping
```

---

## Production Deployment

### 1. Build and Start

```bash
cp .env.example .env
# Edit .env for production: strong SECRET_KEY, real API credentials, restricted origins
docker compose -f docker-compose.prod.yml up -d --build
```

### 2. Production Compose Features

- Resource limits on all services
- Restart policies (`unless-stopped`)
- Healthchecks on the API container
- Migrations run automatically on container start via `scripts/entrypoint.sh`

### 3. Security Checklist

- [ ] Generate a strong `SECRET_KEY` (e.g., `openssl rand -hex 32`).
- [ ] Restrict `ALLOWED_ORIGINS` to your actual frontend domain(s).
- [ ] Set `REDIS_PASSWORD` in production.
- [ ] Use real Amazon and eBay API credentials (not test/sandbox if live trading).
- [ ] Place a reverse proxy (Traefik, Nginx, or cloud load balancer) in front of the API for TLS termination.
- [ ] Consider running database migrations in a one-off init container rather than on every app startup if scaling API to multiple replicas.
- [ ] Enable PostgreSQL backups and point-in-time recovery.

### 4. Scaling Workers

Increase the number of Celery worker replicas:

```bash
docker compose -f docker-compose.prod.yml up -d --scale worker=4
```

Ensure your PostgreSQL connection pool and Redis instance can handle the increased concurrency.

### 5. Health Monitoring

The API container exposes a healthcheck endpoint:

```bash
curl -f http://localhost:8000/api/v1/health
```

A `200 OK` response indicates the application is running and the database is reachable.

---

## Docker Image Details

### Multi-Stage Build

1. **Builder stage** (`python:3.13-slim` + `build-essential` + `libpq-dev`)
   - Compiles Python dependencies into a virtual environment.
2. **Runtime stage** (`python:3.13-slim` + `libpq5`)
   - Copies the pre-built virtual environment.
   - Runs as non-root `appuser`.
   - Exposes port `8000`.

### Entrypoint

`scripts/entrypoint.sh` performs:
1. Waits for PostgreSQL to be reachable.
2. Runs `alembic upgrade head`.
3. Starts the application server (`uvicorn`).

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| API returns `500` on startup | Missing required env var | Check `SECRET_KEY`, `DATABASE_URL`, `DATABASE_URL_SYNC` |
| Celery tasks not executing | Redis unreachable | Verify `REDIS_HOST` and `REDIS_PORT`; check `docker compose logs redis` |
| eBay API returns `401` | Invalid/expired OAuth token | Verify `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` |
| Amazon search returns empty | Invalid PA-API credentials or throttling | Check `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY`; verify rate limits |
| Database migration fails | Sync URL incorrect | Ensure `DATABASE_URL_SYNC` uses `postgresql://` (not `postgresql+asyncpg://`) |
