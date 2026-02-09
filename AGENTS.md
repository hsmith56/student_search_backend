# AGENTS.md

## Project Summary
- Name: `student-search-api`
- Purpose: FastAPI backend for searching and managing student profile data, user auth, favorites, and feedback.
- Runtime: Python `>=3.9.2` with `uv`.
- Primary storage: SQLite database file `user_auth.db` in repo root.

## Tech Stack
- API framework: FastAPI
- Data models: Pydantic (`models/`)
- Persistence: `sqlite3` via `utils/db.py`
- External integration: Beacon API refresh scripts in `utils/beacon_*`
- Reverse proxy/TLS (local/prod edge): `nginx.conf`

## Local Setup
1. Install dependencies:
```powershell
uv sync
```
2. Ensure `.env` includes Beacon credentials used by refresh scripts:
```env
beacon_username=...
beacon_password=...
```
3. Start API server (dev):
```powershell
uv run fastapi dev
```
4. Alternative run command:
```powershell
uv run fastapi run
```

## Architecture Map
- `main.py`
  - App creation, CORS setup, router registration.
  - Protects most routers with `Depends(get_current_user)`.
- `routers/`
  - `auth.py`: login/logout/register/session+refresh cookie auth.
  - `students.py`: full student fetch, filtered search, Beacon-triggered DB refresh.
  - `users.py`: current user + favorites CRUD.
  - `feedback.py`: feedback CRUD.
  - `misc.py`: count/country/last-update helper endpoints.
- `utils/db.py`
  - Database schema initialization (`initialize_db()` runs at import time).
  - CRUD for users, students, favorites, feedback, admin metadata.
- `utils/search_filters.py`
  - Filtering pipeline for `SearchFilters`.
- `models/`
  - `student.py`: `BasicStudent`, `FullStudent`.
  - `search_filters.py`: immutable (`frozen=True`) request filter model.

## Auth and Session Notes
- Auth is cookie-based.
- Session and refresh token stores are in-memory dicts in `routers/auth.py`:
  - Restarting the API invalidates active sessions/tokens.
  - This is expected with current design.
- Most routes are protected in `main.py`, not per-route decorator.

## Database and Data Refresh Notes
- SQLite file path is hardcoded as `user_auth.db`.
- Schema creation/migration-lite logic is centralized in `utils/db.py`.
- Student search uses `@lru_cache` in `routers/students.py`:
  - If student data changes, clear cache (`apply_filters.cache_clear()`).
- Beacon refresh flow touches both stage scripts:
  - Stage 1 discovers updates.
  - Stage 2 hydrates full student details.

## Development Rules For Agents
- Keep changes minimal and scoped to the task.
- Preserve existing route prefixes and response shapes unless explicitly asked to change API contracts.
- Prefer updating utility functions in `utils/db.py` instead of duplicating DB logic inside routers.
- When editing schema behavior, keep migrations backward-compatible for existing `user_auth.db`.
- Keep type hints consistent with existing style (pyright basic mode).
- Avoid committing secrets or local artifacts (`.env`, `bearer_token`, `*.db`, logs/temp data).

## Validation Checklist
- Run server and confirm startup:
```powershell
uv run fastapi dev
```
- Smoke-check critical endpoints:
1. `POST /auth/login`
2. `GET /auth/me`
3. `POST /students/search`
4. `GET /user/favorites`
5. `POST /feedback/`
- If touching refresh logic, verify `.env` credentials and Beacon token generation path (`utils/beacon_auth.py`).

## Known Project Quirks
- `README.md` is intentionally minimal; rely on code structure above.
- `utils/db.py` executes `initialize_db()` on import, so importing DB utilities has side effects.
- `test.py` is not a formal automated test suite; treat it as an ad-hoc script.
