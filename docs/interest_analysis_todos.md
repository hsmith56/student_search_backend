# Interest Analysis Dashboard Endpoint TODOs

## Context

A new `director` account type has been added. Directors should behave like RPM users, with the additional ability to access the upcoming dashboard utility endpoint. Admin users should also be allowed to access the endpoint.

## Remaining TODOs

### 1. Define “available students to place”

Confirm the exact `placement_status` values that should count as available.

Suggested starting point:
- Include statuses like `Unassigned` / equivalent available statuses.
- Exclude placed, allocated, withdrawn, inactive, or unavailable statuses.

Implementation note:
- Inspect current distinct values from `student_full_view.placement_status` before coding the final filter.

### 2. Add interest-count repository function

File: `repositories/students.py`

Add a function such as:

```python
def get_available_student_interest_counts() -> dict[str, int]:
    ...
```

Expected behavior:
- Query `student_full_view` for available students only.
- Read `selected_interests` JSON.
- Ignore null/empty/malformed interest payloads safely.
- Normalize interest labels consistently, likely `strip()` and lower-case.
- Count each interest once per student unless product wants duplicate entries counted.
- Return a plain object like:

```json
{
  "basketball": 16,
  "fencing": 4
}
```

### 3. Add dashboard router

New file: `routers/dashboard.py`

Suggested endpoint:

```python
@router.get("/interests", response_model=dict[str, int])
def get_interest_analysis(current_user: dict = Depends(get_current_user)) -> dict[str, int]:
    ...
```

Suggested router config:

```python
router = APIRouter(prefix="/dashboard", tags=["dashboard"])
```

### 4. Add dashboard role guard

Only allow:
- `admin`
- `director`

Reject:
- `rpm`
- `lc`

Suggested helper:

```python
def _require_director_or_admin(current_user: dict) -> None:
    if current_user["account_type"] not in {"admin", "director"}:
        raise HTTPException(status_code=403, detail="Forbidden")
```

### 5. Wire router into app

File: `main.py`

- Import `dashboard` from `routers`.
- Include router with existing auth dependency pattern:

```python
app.include_router(dashboard.router, dependencies=[Depends(get_current_user)])
```

### 6. Validate behavior

Recommended checks:
- Compile changed files:

```bash
uv run python -m py_compile repositories/students.py routers/dashboard.py main.py
```

- Import app:

```bash
uv run python -c "import main"
```

- Verify authorization behavior:
  - `admin` -> `200`
  - `director` -> `200`
  - `rpm` -> `403`
  - `lc` -> `403`

- Verify response shape is a JSON object with string keys and integer counts.

### 7. Optional tests

If adding tests, cover:
- Counts interests for available students.
- Excludes unavailable/placed statuses.
- Handles `selected_interests` of `NULL`, `[]`, malformed JSON.
- Does not allow RPM/LC access.
