# Student Search API (Backend)

## Run
- `uv run fastapi dev`
- `uv run fastapi run`
- `uv run python scripts/refresh_students.py` (manual refresh script)
- `uv run python scripts/switch_allocated_to_unassigned.py --count 5` allows for easy swapping of students from allocated to unassigned for testing
- `uv run python scripts/clear_news_feed.py` clears all feed events
- `uv run python scripts/add_news_feed_event.py --student-id 12345` inserts a feed event (`Unassigned -> Allocated`) that will be broadcast if websocket notifier is running

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
- News feed endpoint (read-only): `GET /news_feed?limit=100` returns placement event items ordered most-recent first.

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
