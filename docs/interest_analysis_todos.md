# Interest Analysis Dashboard Endpoint

## Status

Implemented.

## Behavior

- Endpoint: `GET /dashboard/interests`
- Access: `admin` + `director`
- Rejected roles: `rpm` + `lc`
- Student filter: `placement_status = "Allocated"`
- Interest source: `student_full_view.selected_interests`
- Counts: case-insensitive, each interest counted once per student
- Response labels: title case
- Response shape: JSON object, `dict[str, int]`

Example:

```json
{
  "Basketball - Playing": 30,
  "Fencing": 4
}
```

## Files

- `repositories/students.py`
  - `get_available_student_interest_counts()`
- `routers/dashboard.py`
  - `GET /dashboard/interests`
  - `_require_director_or_admin()`
- `main.py`
  - dashboard router registration

## Validation

Completed:

```bash
uv run ruff check repositories/students.py routers/dashboard.py main.py routers/admin.py routers/auth.py routers/rpm.py repositories/admin.py repositories/users.py
uv run python -m py_compile repositories/students.py routers/dashboard.py main.py routers/admin.py routers/auth.py routers/rpm.py repositories/admin.py repositories/users.py
uv run python -c "import main; print('main import ok')"
```

## Optional future work

- Add automated tests for repo fn + dashboard guard.
- Exercise live HTTP endpoint with real cookies for all roles.
- Rename legacy `/rpm/*` routes only if frontend can absorb a breaking API change.
- Rename `manager_id` fields only with coordinated DB/API/frontend migration.
