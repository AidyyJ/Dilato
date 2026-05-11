# Amazon-to-eBay Reselling Automation

Backend API for automating Amazon-to-eBay reselling. Built with **FastAPI**, **SQLAlchemy** (async PostgreSQL), **Celery** (Redis), and containerised with **Docker**.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/install/) v2+
- (Optional) Python 3.13+ if you want to run tests or linting outside Docker

---

## Quick Start (Local Development)

1. **Clone the repository** and change into the project root.

2. **Copy the environment template** and fill in your real credentials:

   ```bash
   cp .env.example .env
   # Edit .env with your Amazon PA-API and eBay API keys
   ```

3. **Build and start the stack**:

   ```bash
   docker compose up --build
   ```

   The API will be available at **http://localhost:8000**.

4. **Open the interactive docs**:

   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### Services started

| Service | Description | Port |
|---------|-------------|------|
| `api`   | FastAPI application server | `8000` |
| `worker`| Celery worker (price/stock sync, eBay tasks) | — |
| `beat`  | Celery beat scheduler | — |
| `db`    | PostgreSQL 16 | `5432` |
| `redis` | Redis 7 (broker + result backend) | `6379` |

The `api` service runs with `--reload` so code changes are reflected immediately.

---

## Production Deployment

Use the production Compose file which includes resource limits, restart policies, and health checks:

```bash
cp .env.example .env
# Edit .env for production values (strong SECRET_KEY, real API credentials, etc.)
docker compose -f docker-compose.prod.yml up -d --build
```

**Notes for production:**

- Change `SECRET_KEY` to a cryptographically secure random string.
- Restrict `ALLOWED_ORIGINS` to your actual frontend domain(s).
- Consider running database migrations in a one-off init container rather than on every app startup if you scale the API to multiple replicas.
- Use a reverse proxy (e.g., Traefik, Nginx) in front of the API for TLS termination.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | **required** | Async PostgreSQL connection string |
| `DATABASE_URL_SYNC` | **required** | Sync PostgreSQL connection string (Alembic) |
| `REDIS_HOST` | `redis` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_PASSWORD` | `—` | Redis password (empty = no auth) |
| `REDIS_URL` | auto-built from components | Redis connection string (overrides components) |
| `CELERY_BROKER_URL` | auto-built from components | Celery broker (overrides components) |
| `CELERY_RESULT_BACKEND` | auto-built from components | Celery result backend (overrides components) |
| `SECRET_KEY` | **required** | JWT signing key (no default for security) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token lifetime |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:8000` | CORS allowed origins (comma-separated) |
| `RATE_LIMIT_DEFAULT` | `100/minute` | Default rate limit |
| `RATE_LIMIT_AUTH` | `10/minute` | Auth endpoint rate limit |
| `AMAZON_ACCESS_KEY` | — | Amazon PA-API access key |
| `AMAZON_SECRET_KEY` | — | Amazon PA-API secret key |
| `AMAZON_PARTNER_TAG` | — | Amazon associate tag |
| `AMAZON_HOST` | `webservices.amazon.com` | Amazon API host |
| `AMAZON_REGION` | `us-east-1` | Amazon API region |
| `EBAY_CLIENT_ID` | — | eBay REST API client ID |
| `EBAY_CLIENT_SECRET` | — | eBay REST API client secret |
| `EBAY_DEV_ID` | — | eBay developer ID |
| `EBAY_RU_NAME` | — | eBay RuName (OAuth redirect) |
| `EBAY_SITE_ID` | `0` | eBay site ID (`0` = US) |
| `EBAY_API_BASE_URL` | `https://api.ebay.com` | eBay API base URL |
| `DEFAULT_PROFIT_MARGIN_THRESHOLD` | `0.15` | Minimum profit margin for sourcing |
| `DEFAULT_MAX_PRICE_USD` | `200.0` | Maximum product price filter |
| `DEFAULT_MIN_PRICE_USD` | `5.0` | Minimum product price filter |
| `STOCK_SYNC_INTERVAL` | `21600` | Stock sync interval in seconds (6h) |
| `PRICE_SYNC_INTERVAL` | `7200` | Price sync interval in seconds (2h) |
| `DEFAULT_AVAILABLE_QUANTITY` | `5` | Default listing quantity |
| `PRICE_SYNC_MIN_DELTA_PERCENT` | `1.0` | Minimum price delta % before updating eBay |

---

## Development Tips

### Run database migrations manually

```bash
docker compose exec api alembic upgrade head
```

### Create a new migration

```bash
docker compose exec api alembic revision --autogenerate -m "description"
```

### Run tests

```bash
# Inside the API container
docker compose exec api pytest

# Or locally with a virtual environment
pytest
```

### Inspect Celery tasks

```bash
# Worker logs
docker compose logs -f worker

# Beat logs
docker compose logs -f beat

# Ping workers
docker compose exec worker celery -A app.tasks.celery_app inspect ping
```

---

## Project Structure

```
.
├── app/
│   ├── api/v1/endpoints/   # FastAPI route handlers
│   ├── core/               # Config, database, security, limiter
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic (Amazon/eBay APIs, pricing, etc.)
│   └── tasks/              # Celery tasks & app
├── alembic/                # Database migrations
├── scripts/
│   ├── entrypoint.sh       # Container entrypoint (migrations + start)
│   └── run_migrations.sh   # Alembic migration runner
├── tests/                  # Pytest test suite
├── Dockerfile              # Multi-stage production image
├── docker-compose.yml      # Local development stack
├── docker-compose.prod.yml # Production stack
├── .env.example            # Environment variable template
└── README.md               # This file
```

---

## License

Private — for personal use only.
