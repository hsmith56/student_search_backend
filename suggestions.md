# Project Structure and Architecture Suggestions

## Scope
This review focuses on project structure, file layout, and architectural patterns in the current backend repository.

## Current Layout (Observed)
- Top-level code modules: `main.py`, `routers/`, `models/`, `utils/`
- Infra/config in root: `nginx.conf`, `.env`, `.python-version`, `pyproject.toml`
- Runtime artifacts in root: `user_auth.db`, `bearer_token`, `logs/`, `temp/`, `__pycache__/`
- Data assets in `data/` (JSON mappings + large student payload files)
- No dedicated `tests/` package; ad-hoc `test.py` script in root

## Priority Findings

### 1) Import-time Side Effects (High)
- `utils/db.py` runs `initialize_db()` at import.
- `routers/students.py` runs `db.update_time()` at import.
- `utils/beacon_refresh_stage2.py` performs auth/token work and file loading at import.
- `test.py` executes code directly.

Why this matters:
- App startup can trigger DB mutations, external network calls, and unexpected failures.
- Imports should be safe, deterministic, and side-effect minimal.

### 2) Mixed Responsibilities in `utils/` (High)
- `utils/db.py` is a large mixed module containing schema creation, user CRUD, feedback CRUD, student persistence, and serialization helpers.
- `utils/beacon_refresh_stage1.py` / `stage2.py` mix HTTP client concerns, transformation logic, orchestration, and persistence calls.

Why this matters:
- Hard to test and reason about.
- Changes risk regressions in unrelated features.

### 3) Router Layer Is Doing Service/Data Work (High)
- Routers call deep DB functions and refresh workflows directly.
- Domain logic is spread across router files and utility modules.

Why this matters:
- API layer should stay thin; business logic should live in services/use-cases.

### 4) Configuration Is Not Centralized (High)
- Hardcoded values in code: DB filename, CORS origins, TLS/domain assumptions.
- Beacon auth uses `.env`, but settings are not managed from a single typed config module.

Why this matters:
- Harder environment portability and safer deployment.

### 5) API Contract/HTTP Semantics Gaps (Medium)
- `GET /students/update_db` mutates state and performs heavy refresh work.
- `routers/misc.py` returns sets (`{value}`) instead of stable JSON objects for counts/timestamps.

Why this matters:
- Unexpected behavior for clients and poor API consistency.

### 6) Security and Session Architecture (Medium)
- Auth tokens/sessions are in-memory dictionaries (`routers/auth.py`).
- Password hashing is SHA-256 while `bcrypt` is already listed as dependency.

Why this matters:
- In-memory sessions do not survive restarts or scale horizontally.
- SHA-256 is not appropriate for password storage.

### 7) Testing/Layout Gaps (Medium)
- No formal `tests/` directory with automated unit/integration tests.
- `test.py` is not a reliable or maintainable validation path.

### 8) Repo Hygiene (Medium)
- Root contains runtime/generated files.
- `.gitignore` currently ignores broad patterns like `*.json`, which can hide important config/test fixtures.

## Recommended Target Layout
Use a package-first layout so app code is separated from runtime artifacts and scripts.

```text
Backend/
  src/
    student_search_api/
      main.py
      api/
        deps.py
        v1/
          router.py
          auth.py
          students.py
          users.py
          feedback.py
          misc.py
      core/
        config.py
        security.py
        logging.py
      db/
        connection.py
        migrations/
      repositories/
        users.py
        students.py
        feedback.py
      services/
        auth_service.py
        student_search_service.py
        beacon_refresh_service.py
      integrations/
        beacon_client.py
      schemas/
        student.py
        filters.py
        auth.py
        feedback.py
  scripts/
    refresh_students.py
    bootstrap_admin.py
  tests/
    unit/
    integration/
  data/
    reference/
      sports_interests.json
      state_mappings.json
  infra/
    nginx.conf
  pyproject.toml
  README.md
  AGENTS.md
  suggestions.md
```

## Incremental Migration Plan (No Big-Bang Rewrite)

### Phase 1: Safety and Cleanup
- Remove import-time side effects; move init/refresh calls into explicit startup hooks or script entrypoints.
- Move `test.py` behavior into `scripts/` and/or `tests/`.
- Replace `print()` with structured logging.
- Change mutating route from `GET` to `POST` (or background job trigger endpoint).

### Phase 2: Configuration and Boundaries
- Add `core/config.py` (Pydantic settings) for DB path, CORS origins, Beacon credentials, environment mode.
- Split `utils/db.py` into repository modules by domain (`users`, `students`, `feedback`).
- Create `integrations/beacon_client.py` with timeouts/retries and token-refresh handling.

### Phase 3: Service Layer
- Introduce service modules used by routers:
  - `auth_service`
  - `student_search_service`
  - `beacon_refresh_service`
- Keep routers thin: request parsing, response shaping, dependency injection only.

### Phase 4: Database and Test Hardening
- Introduce migration tooling (Alembic or equivalent migration scripts for SQLite).
- Add tests:
  - unit tests for filter logic
  - integration tests for auth/session behavior
  - API tests for search/favorites/feedback routes

## Concrete Quick Wins (High ROI)
1. Remove top-level `db.update_time()` call from import path in `routers/students.py`.
2. Stop auth/token generation at import in `utils/beacon_refresh_stage2.py`; initialize lazily in function scope.
3. Convert `GET /students/update_db` to `POST /students/refresh` with explicit intent.
4. Move DB file and token paths to config (`core/config.py`) instead of hardcoded literals.
5. Replace SHA-256 password hashing with `bcrypt` (already available dependency).
6. Normalize response shapes in `routers/misc.py` to objects, e.g. `{"count": 123}`.
7. Create `tests/` and migrate `test.py` into proper automated tests.

## Suggested README Improvements
- Add a real setup section (`uv sync`, env vars, run commands).
- Document API route groups and auth model.
- Document data refresh workflow and operational cautions.
- Add development workflow (`lint`, `type-check`, `test`).

## Suggested `.gitignore` Adjustment
- Narrow broad ignore rule `*.json` to specific generated JSON files only.
- Keep reference data files (`data/reference/*.json`) versioned and explicit.

