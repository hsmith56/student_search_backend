# Student Search API (Backend)

## Run
- `uv run fastapi dev`
- `uv run fastapi run`
- `uv run python scripts/refresh_students.py` (manual refresh script)

## .env Configuration
The app now reads centralized settings from `.env` via `core/config.py`.

```env
# Optional app settings
APP_NAME=student-search-api
DATABASE_PATH=./user_auth.db
BEARER_TOKEN_PATH=./bearer_token
CORS_ORIGINS=https://localhost,http://localhost,https://hsmithtech.com,https://www.hsmithtech.com,*

# Beacon integration
BEACON_BASE_URL=https://api.ciee.org
BEACON_THREADS=16
BEACON_USERNAME=...
BEACON_PASSWORD=...
```

## API Notes
- Student refresh endpoint is mutating and now uses `POST /students/update_db`.
