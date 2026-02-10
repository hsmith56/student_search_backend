# Raspberry Pi Deployment Guide (`student-search-api` + React + Nginx)

## Recommendation (Best Fit for Your Current Code)
Use this architecture on the Pi:
- `nginx` on ports `80/443` (TLS termination)
- `React` built as static files, served by nginx
- `FastAPI` as a `systemd` service on `127.0.0.1:8000`
- SQLite file on local disk (`user_auth.db`)

Why this is the best starting point:
- Lightweight for Raspberry Pi
- Minimal moving parts
- Matches your current nginx reverse-proxy design
- Easy to debug and maintain

## Important Project Constraints
- Auth/session state is currently in memory (`routers/auth.py`).
- Because of that, run **one backend process** (`workers=1`).
- If backend restarts, sessions/refresh tokens reset (expected with current design).
- Cookies are set with `secure=True` and `samesite="none"`, so HTTPS is required in production.

## Option Comparison

### Option A (Recommended): Native services + nginx
- FastAPI via `uvicorn` + `systemd`
- React built once and served by nginx
- Best balance of speed, reliability, and low overhead on Pi

### Option B: Docker Compose
- Cleaner isolation and reproducible deploys
- Slightly more RAM/CPU overhead on Raspberry Pi
- Good if you already use Docker heavily

### Option C: Node-served React/SSR behind nginx
- Needed only if your frontend requires SSR runtime (e.g., Next.js app router/SSR)
- More resource usage than static frontend hosting

## 1) Raspberry Pi Host Setup
Assumes Raspberry Pi OS 64-bit or Ubuntu Server 64-bit.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y nginx curl git build-essential sqlite3
```

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2) Backend Setup (`student_search_backend`)

```bash
cd /opt
sudo git clone <your-backend-repo-url> student_search_backend
sudo chown -R $USER:$USER /opt/student_search_backend
cd /opt/student_search_backend
uv sync
```

Create `.env` with production values (example):

```env
ENVIRONMENT=production
DATABASE_PATH=./user_auth.db
BEARER_TOKEN_PATH=./bearer_token
CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com
BEACON_USERNAME=...
BEACON_PASSWORD=...
LOG_LEVEL=INFO
```

## 3) Backend `systemd` Service
Create `/etc/systemd/system/student-search-api.service`:

```ini
[Unit]
Description=Student Search FastAPI
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/student_search_backend
Environment=PATH=/home/pi/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/pi/.local/bin/uv run uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now student-search-api
sudo systemctl status student-search-api
```

## 4) Frontend Deployment (React)
Build frontend in its own repo and copy build artifacts to nginx web root.

Example (Vite/CRA style output):

```bash
# In frontend repo
npm ci
npm run build

# Copy output to Pi web root (adjust dist/build path)
sudo mkdir -p /var/www/student-search-frontend
sudo cp -r dist/* /var/www/student-search-frontend/
```

## 5) nginx Config (Static React + FastAPI + WebSocket)
Use a production server block like:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    root /var/www/student-search-frontend;
    index index.html;

    # React SPA routing
    location / {
        try_files $uri /index.html;
    }

    # FastAPI endpoints, stripping /api prefix
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }

    # Placement notifications websocket
    location = /notifications/ws/placements {
        proxy_pass http://127.0.0.1:8000/notifications/ws/placements;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
    }
}
```

Enable and validate:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 6) TLS Certificate (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## 7) Deploy/Update Workflow
Backend update:

```bash
cd /opt/student_search_backend
git pull
uv sync
sudo systemctl restart student-search-api
```

Frontend update:
- Rebuild frontend artifacts and copy them to `/var/www/student-search-frontend/`
- `sudo systemctl reload nginx`

## 8) Operational Checks
- Backend logs: `journalctl -u student-search-api -f`
- nginx logs: `/var/log/nginx/access.log` and `/var/log/nginx/error.log`
- Health checks:
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `POST /api/students/search`
  - `GET /api/user/favorites`
  - `POST /api/feedback/`

## 9) SQLite Backup (Recommended)
Run periodic backups (cron/systemd timer):

```bash
sqlite3 /opt/student_search_backend/user_auth.db ".backup '/opt/student_search_backend/backups/user_auth_$(date +%F_%H%M%S).db'"
```

Keep at least daily backups before refresh jobs or app upgrades.

## 10) When to Move Beyond This Setup
Move to Postgres + Redis if you need:
- More concurrent writes
- Shared session/token store across multiple backend instances
- Horizontal scaling across devices/containers

Until then, the single-node Pi deployment above is the most practical and stable path.
