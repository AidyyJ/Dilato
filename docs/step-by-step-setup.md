# Dilato Step-By-Step Setup

This is a strict checklist you can follow in order. It covers:

- Local setup for development/testing.
- Hostinger VPS setup for production deployment.

If you follow each step exactly, you will have:

- Backend services running in Docker (`api`, `worker`, `beat`, `db`, `redis`).
- Dashboard running as a separate process.
- Nginx reverse proxy with HTTPS.

## A. Local Setup (From Zero)

### Step 1. Install prerequisites

1. Install Docker Desktop (or Docker Engine) with Compose v2.
2. Install Node.js 20+ and npm.
3. Confirm tools:

```bash
docker --version
docker compose version
node -v
npm -v
```

### Step 2. Open project and create env file

1. Open terminal at project root.
2. Copy env template:

```bash
cp .env.example .env
```

3. Edit `.env` and set at minimum:
   - `DATABASE_URL`
   - `DATABASE_URL_SYNC`
   - `SECRET_KEY`
4. Add these too for consistency with production:
   - `POSTGRES_USER=postgres`
   - `POSTGRES_PASSWORD=postgres`
   - `POSTGRES_DB=reseller`

### Step 3. Start backend Docker stack

```bash
docker compose up --build -d
```

### Step 4. Verify backend is healthy

```bash
docker compose ps
docker compose logs -f api
curl http://localhost:8000/api/v1/health
```

Expected result: health endpoint returns success.

### Step 5. Optional backend validation

```bash
docker compose exec api alembic upgrade head
docker compose exec api pytest
docker compose logs -f worker
docker compose logs -f beat
docker compose exec worker celery -A app.tasks.celery_app inspect ping
```

### Step 6. Start dashboard

1. Open a second terminal.
2. Run:

```bash
cd dashboard
npm ci
```

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

### Step 7. Open the apps

1. API docs: `http://localhost:8000/docs`
2. Dashboard: `http://localhost:3000`

Note: dashboard auth integration is not complete yet, so some live protected API flows will not work end-to-end.

## B. Hostinger VPS Setup (Ubuntu)

### Step 1. Prepare DNS

Create A records:

1. `api.your-domain.tld` -> your VPS public IP
2. `app.your-domain.tld` -> your VPS public IP

### Step 2. SSH into VPS and update packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg lsb-release git ufw nginx
```

### Step 3. Configure firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
sudo ufw status
```

### Step 4. Install Docker and Compose plugin

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

### Step 5. Install Node.js 20+

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v
npm -v
```

### Step 6. Clone project

```bash
sudo mkdir -p /opt/dilato
sudo chown -R $USER:$USER /opt/dilato
git clone <your-repo-url> /opt/dilato
cd /opt/dilato
cp .env.example .env
```

### Step 7. Configure production env

Edit `.env` and set all required values.

Minimum required production values:

1. `POSTGRES_USER`
2. `POSTGRES_PASSWORD`
3. `POSTGRES_DB`
4. `DATABASE_URL` (async)
5. `DATABASE_URL_SYNC` (sync)
6. `SECRET_KEY`
7. `REDIS_PASSWORD`
8. `ALLOWED_ORIGINS=https://app.your-domain.tld`

Generate a secret:

```bash
openssl rand -hex 32
```

### Step 8. Start backend production services

```bash
cd /opt/dilato
docker compose -f docker-compose.prod.yml up -d --build
```

### Step 9. Verify backend services

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
curl http://127.0.0.1:8000/api/v1/health
```

### Step 10. Build dashboard for production

```bash
cd /opt/dilato/dashboard
npm ci
NEXT_PUBLIC_API_URL=https://api.your-domain.tld npm run build
```

### Step 11. Create dashboard systemd service

Create file: `/etc/systemd/system/dilato-dashboard.service`

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

Then run:

```bash
sudo chown -R www-data:www-data /opt/dilato/dashboard
sudo systemctl daemon-reload
sudo systemctl enable --now dilato-dashboard
sudo systemctl status dilato-dashboard --no-pager
```

### Step 12. Configure Nginx reverse proxy

Create file: `/etc/nginx/sites-available/dilato`

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

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/dilato /etc/nginx/sites-enabled/dilato
sudo nginx -t
sudo systemctl reload nginx
```

### Step 13. Enable HTTPS (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.your-domain.tld -d app.your-domain.tld
sudo certbot renew --dry-run
```

### Step 14. Final validation

```bash
curl -I https://api.your-domain.tld/api/v1/health
curl -I https://app.your-domain.tld
docker compose -f /opt/dilato/docker-compose.prod.yml ps
sudo systemctl status dilato-dashboard --no-pager
```

## C. Day-2 Commands

Backend update:

```bash
cd /opt/dilato
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Dashboard update:

```bash
cd /opt/dilato/dashboard
npm ci
NEXT_PUBLIC_API_URL=https://api.your-domain.tld npm run build
sudo systemctl restart dilato-dashboard
```

Logs:

```bash
docker compose -f /opt/dilato/docker-compose.prod.yml logs -f api
docker compose -f /opt/dilato/docker-compose.prod.yml logs -f worker
docker compose -f /opt/dilato/docker-compose.prod.yml logs -f beat
sudo journalctl -u dilato-dashboard -f
```
