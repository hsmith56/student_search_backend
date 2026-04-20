# Autoresearch: Improve DB querying, schema startup, and duplication in repository layer

## Objective
Improve database-layer performance and maintainability by reducing runtime in representative DB workloads (schema init + common read queries) while reducing duplicated query/connection patterns where it helps. Preserve API behavior and avoid benchmark overfitting.

## Metrics
- **Primary**: `total_ms` (ms, lower is better) — median runtime of the database workload benchmark.
- **Secondary**: `p95_total_ms`, `schema_ms`, `users_ms`, `students_ms`, `favorites_ms`.

## How to Run
`./autoresearch.sh`

## Files in Scope
- `repositories/admin.py` — schema initialization and migration-lite behavior.
- `repositories/users.py` — user-related query paths with repeated patterns.
- `repositories/students.py` — student read/query helpers.
- `repositories/base.py` — connection factory behavior.
- `scripts/benchmark_db_layer.py` — DB benchmark workload.
- `autoresearch.sh` — benchmark runner.

## Off Limits
- Route contracts and auth semantics.
- Non-DB functional behavior changes.
- External services/integrations.

## Constraints
- Keep SQLite schema backward-compatible with existing `user_auth.db`.
- No benchmark cheating / no overfitting to one query path.
- No new dependencies.

## Tooling Requirements (benchmark + loop)
- Run benchmark via `./autoresearch.sh` from repo root.
- Script must bootstrap/use Linux `uv` internally for `run_experiment` shells.
- Do not rely on Windows `.venv/Scripts/python.exe` in experiment runner.
- Benchmark must emit structured `METRIC ...` lines.

## What's Been Tried
- Previous session landed major student search wins; this session retargets DB/query/schema concerns.
- Need fresh baseline for DB-layer workload before optimization.
