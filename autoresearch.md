# Autoresearch: Optimize students search endpoint latency

## Objective
Improve backend runtime for the `POST /students/search` workload by reducing time spent in filtering and result shaping for representative requests. The benchmark executes the same `run_student_search()` code path used by API routes and measures end-to-end search work (filtering, sorting, pagination, and response model conversion).

## Metrics
- **Primary**: `total_ms` (ms, lower is better) — median total time for one mixed search workload batch.
- **Secondary**: `p95_total_ms`, `total_results` — tail-latency and correctness/shape guardrail.

## How to Run
`./autoresearch.sh` — outputs structured `METRIC name=value` lines.

## Files in Scope
- `routers/students.py` — search orchestration, sorting, pagination, cache behavior.
- `utils/search_filters.py` — filter pipeline and hot filter functions.
- `repositories/students.py` — student row mapping/data access used by search.
- `models/search_filters.py` — filter model normalization behavior.
- `scripts/benchmark_students_search.py` — benchmark workload definition.
- `autoresearch.sh` — benchmark runner.

## Off Limits
- Auth/session semantics and route paths.
- Beacon refresh/network flows unless directly required for search latency.
- DB schema and migration behavior unrelated to search performance.

## Constraints
- Preserve existing API response shape and semantics for student search.
- No new third-party dependencies.
- Keep behavior backward compatible for existing `user_auth.db`.

## What's Been Tried
- Baseline not run yet.
