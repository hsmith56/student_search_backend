# Autoresearch: Optimize students search endpoint latency

## Objective
Reduce `POST /students/search` runtime for representative workloads without changing behavior or overfitting benchmarks.

## Metrics
- **Primary**: `total_ms` (ms, lower is better)
- **Secondary**: `p95_total_ms`, `total_results`, `student_count`, `baseline_all_ms`, `structured_filters_ms`, `free_text_ms`, `favorites_ms`

## How to Run
`./autoresearch.sh`

## Files in Scope
- `routers/students.py`
- `utils/search_filters.py`
- `repositories/students.py`
- `models/search_filters.py`
- `scripts/benchmark_students_search.py`
- `autoresearch.sh`

## Off Limits
- API contracts, auth/session semantics
- Non-search schema/network behavior

## Constraints
- No benchmark cheating/overfitting
- Preserve response shapes and correctness
- No new dependencies

## What's Been Tried
- Full-student cache + free-text matcher optimizations already landed.
- Free-text case still dominates the benchmark; optimize per-student scoring overhead next.
