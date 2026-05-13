# Deployment Guide

This guide explains how to run Dilato locally and deploy it to a VPS, with explicit steps for a Hostinger VPS.

The project currently has two runtime planes:

- Backend plane in Docker: FastAPI API, Celery worker, Celery beat, PostgreSQL, Redis.
- Dashboard plane outside Docker: Next.js app under `dashboard/`.

## 1. What You Are Deploying

Backend services (Docker):

- `api` on port `8000`
- `worker` (Celery)
- `beat` (Celery Beat)
- `db` (PostgreSQL 16)
- `redis` (Redis 7)

Frontend service (separate process):

- Next.js dashboard (typically port `3000`), reverse-proxied by Nginx.

## 2. Prerequisites

Local machine:

- Docker 24+
- Docker Compose v2+
- Node.js 20+ and npm (for dashboard)

VPS (Hostinger recommended baseline):

- Ubuntu 22.04 or 24.04
- 2 vCPU / 4 GB RAM minimum
- Docker Engine + Compose plugin
- Nginx
- Node.js 20+
- A domain name and DNS access

## 3. Environment Variables

Copy `.env.example` to `.env` and fill in values.

```bash
cp .env.example .env
```

Required app variables:

- `DATABASE_URL`
- `DATABASE_URL_SYNC`
- `SECRET_KEY`

Required in production compose (must be added manually because `.env.example` does not include them):

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

External API credentials (needed for real integrations):

- `AMAZON_ACCESS_KEY`
- `AMAZON_SECRET_KEY`
- `AMAZON_PARTNER_TAG`
- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`
- `EBAY_DEV_ID`
- `EBAY_RU_NAME`

Strongly recommended production values:

- `REDIS_PASSWORD` (required by `docker-compose.prod.yml`)
- `ALLOWED_ORIGINS` restricted to your frontend domain(s)

Reference production-style values:

```dotenv
POSTGRES_USER=dilato
POSTGRES_PASSWORD=<strong-db-password>
POSTGRES_DB=dilato

DATABASE_URL=postgresql+asyncpg://dilato:<strong-db-password>@db:5432/dilato
DATABASE_URL_SYNC=postgresql://dilato:<strong-db-password>@db:5432/dilato

SECRET_KEY=<openssl-rand-hex-32>
REDIS_PASSWORD=<strong-redis-password>
ALLOWED_ORIGINS=https://app.your-domain.tld
```

## 4. Local Setup (Full Stack Testing)

### 4.1 Start backend stack

From repository root:

```bash
cp .env.example .env
# Edit .env
docker compose up --build -d
```

Verify containers:

```bash
docker compose ps
docker compose logs -f api
curl http://localhost:8000/api/v1/health
```

Useful backend checks:

```bash
docker compose exec api alembic upgrade head
docker compose exec api pytest
docker compose logs -f worker
docker compose logs -f beat
docker compose exec worker celery -A app.tasks.celery_app inspect ping
```

### 4.2 Start dashboard locally

In a separate shell:

```bash
cd dashboard
npm ci
```

Set API URL and run:

Windows PowerShell:

```powershell
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
npm run dev
```

Linux/macOS:

```bash
export NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open:

- API docs: `http://localhost:8000/docs`
- Dashboard: `http://localhost:3000`

Important current limitation:

- Most backend routes are JWT-protected, but the dashboard client does not yet implement login/token handling end-to-end.

## 5. Hostinger VPS Deployment (Step-by-Step)

This section assumes SSH access as `root` or a sudo user.

### 5.1 Provision DNS

Create records pointing to the VPS public IP:

- `A` record: `api.your-domain.tld` -> VPS IP
- `A` record: `app.your-domain.tld` -> VPS IP

### 5.2 Base system hardening

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg lsb-release git ufw nginx
```

Firewall:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
sudo ufw status
```

### 5.3 Install Docker and Compose plugin

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
   "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
   $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
   sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
docker --version
docker compose version
```

### 5.4 Install Node.js 20+

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v
npm -v
```

### 5.5 Clone project and configure env

```bash
sudo mkdir -p /opt/dilato
sudo chown -R $USER:$USER /opt/dilato
git clone <your-repo-url> /opt/dilato
cd /opt/dilato
cp .env.example .env
```

Edit `.env` and set at minimum:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `DATABASE_URL`, `DATABASE_URL_SYNC`
- `SECRET_KEY`
- `REDIS_PASSWORD`
- `ALLOWED_ORIGINS=https://app.your-domain.tld`
- Amazon/eBay credentials if you need live integration

Generate a strong secret:

```bash
openssl rand -hex 32
```

### 5.6 Start backend production stack

```bash
cd /opt/dilato
docker compose -f docker-compose.prod.yml up -d --build
```

Verify:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
curl http://127.0.0.1:8000/api/v1/health
```

Notes:

- The API container runs migrations on startup via `scripts/run_migrations.sh`.
- `scripts/entrypoint.sh` does not actively wait for Postgres; startup ordering is handled by Compose health checks and dependencies.

### 5.7 Deploy dashboard as a systemd service

Build dashboard:

```bash
cd /opt/dilato/dashboard
npm ci
NEXT_PUBLIC_API_URL=https://api.your-domain.tld npm run build
```

Create service file `/etc/systemd/system/dilato-dashboard.service`:

```ini
[Unit]
Description=Dilato Next.js Dashboard
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/dilato/dashboard
Environment=NODE_ENV=production
Environment=NEXT_PUBLIC_API_URL=https://api.your-domain.tld
ExecStart=/usr/bin/npm run start -- -p 3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo chown -R www-data:www-data /opt/dilato/dashboard
sudo systemctl daemon-reload
sudo systemctl enable --now dilato-dashboard
sudo systemctl status dilato-dashboard --no-pager
```

### 5.8 Configure Nginx reverse proxy

Create `/etc/nginx/sites-available/dilato`:

```nginx
server {
      listen 80;
      server_name api.your-domain.tld;

      location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
      }
}

server {
      listen 80;
      server_name app.your-domain.tld;

      location / {
            proxy_pass http://127.0.0.1:3000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
      }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/dilato /etc/nginx/sites-enabled/dilato
sudo nginx -t
sudo systemctl reload nginx
```

### 5.9 Enable TLS with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.your-domain.tld -d app.your-domain.tld
sudo certbot renew --dry-run
```

### 5.10 Post-deploy validation

```bash
curl -I https://api.your-domain.tld/api/v1/health
curl -I https://app.your-domain.tld
docker compose -f /opt/dilato/docker-compose.prod.yml ps
sudo systemctl status dilato-dashboard --no-pager
```

## 6. Operations

### 6.1 Update and redeploy

Backend:

```bash
cd /opt/dilato
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Dashboard:

```bash
cd /opt/dilato/dashboard
npm ci
NEXT_PUBLIC_API_URL=https://api.your-domain.tld npm run build
sudo systemctl restart dilato-dashboard
```

### 6.2 Logs

```bash
docker compose -f /opt/dilato/docker-compose.prod.yml logs -f api
docker compose -f /opt/dilato/docker-compose.prod.yml logs -f worker
docker compose -f /opt/dilato/docker-compose.prod.yml logs -f beat
sudo journalctl -u dilato-dashboard -f
```

### 6.3 Backups

Create periodic Postgres dumps:

```bash
mkdir -p /opt/backups/dilato
docker exec $(docker ps --filter name=db --format '{{.ID}}' | head -n1) \
   pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > /opt/backups/dilato/dilato_$(date +%F).sql
```

Store backups off-server (object storage or remote backup host).

## 7. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| API container restarts repeatedly | Missing `.env` values | Check `SECRET_KEY`, DB URLs, and `REDIS_PASSWORD` in `.env` |
| `db` fails in production compose | Missing `POSTGRES_*` variables | Add `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` to `.env` |
| Dashboard shows API errors | `NEXT_PUBLIC_API_URL` incorrect | Rebuild dashboard with correct API URL and restart service |
| 502 from Nginx | Upstream service not running | Check `docker compose ... ps` and `systemctl status dilato-dashboard` |
| Celery tasks not processing | Worker disconnected from Redis | Verify Redis password and worker logs |
| TLS issuance fails | DNS not propagated or port 80 blocked | Verify A records and firewall (`ufw status`) |

## 8. Current Known Limitations

- The dashboard is not fully integrated with backend JWT auth yet.
- Dashboard deployment is separate from Docker compose.
- Sourcing uses fallback estimate logic and is not a full market-aware eBay pricing engine.

