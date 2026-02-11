# Student Search API (Backend)

## Run
- `uv run fastapi dev`
- `uv run fastapi run`
- `uv run scripts/refresh_students.py` (manual refresh script)
- `uv run scripts/switch_allocated_to_unassigned.py --count 5` allows for easy swapping of students from allocated to unassigned for testing
- `uv run scripts/clear_news_feed.py` clears all feed events and resets the event ID sequence
- `uv run scripts/add_news_feed_event.py --student-id 12345 --first-name Alice` inserts a feed event (`Unassigned -> Allocated`) that will be broadcast if websocket notifier is running
- `uv run python scripts/export_placement_data.py` exports Beacon host placement payloads for placed students to `placement_data.json`
- `uv run python scripts/import_placement_metrics.py` imports `placement_data.json` into `placement_metrics` (skips rows missing `placementDate`)

## Placement Metrics Scripts

Use these scripts together for placement metrics debugging:

1. Export placement data from Beacon for placed students:
```powershell
uv run python scripts/export_placement_data.py
```
This reads placed students from `student_full_view` and writes Beacon host information responses to `placement_data.json` at the repo root.

2. Import placement metrics into SQLite:
```powershell
uv run python scripts/import_placement_metrics.py
```
This upserts into `placement_metrics` using:
- `app_id` (primary key)
- `city`
- `state`
- `placementDate` (required; records missing this are skipped)

Optional: import from a custom JSON path:
```powershell
uv run python scripts/import_placement_metrics.py .\path\to\placement_data.json
```

## Local TLS Certificate (Linux/macOS)
From `Backend/`, generate the local cert/key in the project root (`Student_Search/`):

```bash
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout ../localhost.key \
  -out ../localhost.crt \
  -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Then update `nginx_unix.conf` certificate paths to match your Unix absolute path if needed.

## .env Configuration
The app now reads centralized settings from `.env` via `core/config.py`.

```env
# Optional app settings
APP_NAME=student-search-api
ENVIRONMENT=development
DATABASE_PATH=./user_auth.db
BEARER_TOKEN_PATH=./bearer_token
CORS_ORIGINS=https://localhost,http://localhost,https://hsmithtech.com,https://www.hsmithtech.com,*

# Beacon integration
BEACON_BASE_URL=https://api.ciee.org
BEACON_THREADS=16
BEACON_TIMEOUT_SECONDS=30
BEACON_MAX_RETRIES=3
BEACON_RETRY_BACKOFF_SECONDS=1
LOG_DIR=./log
LOG_FILE_NAME=app.log
LOG_LEVEL=INFO
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=5
LOG_TO_CONSOLE=true
BEACON_USERNAME=...
BEACON_PASSWORD=...
```

## API Notes
- Student refresh endpoint is mutating and now uses `POST /students/update_db`.
- News feed endpoint (read-only): `GET /news_feed?limit=100` returns placement event items ordered most-recent first, including `first_name`.

## WebSocket Notifications (Authenticated)
- Endpoint: `ws://<host>/notifications/ws/placements` (or `wss://` in HTTPS environments)
- Auth required: existing auth cookies from `POST /auth/login`
- Cookie names used by backend:
  - `session_id`
  - `refresh_token`
- Event emitted when a student changes from `Unassigned` to `Allocated`

Example payload:
```json
{
  "type": "student_became_allocated",
  "event": {
    "event_id": 123,
    "student_id": 456,
    "event_type": "status_changed",
    "event_at": "2026-02-09T15:37:39.014138-05:00",
    "placement_state": "Allocated",
    "coordinator_id": null,
    "manager_id": null,
    "status_from": "Unassigned",
    "status_to": "Allocated"
  }
}
```

Frontend notes:
- Make sure login happens first so cookies exist before opening the WebSocket.
- Browser WebSocket connections automatically include matching cookies for the socket URL domain.
- If auth fails, backend rejects the connection with policy violation (`1008`).
