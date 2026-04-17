#!/usr/bin/env bash
set -euo pipefail

python -m py_compile routers/students.py utils/search_filters.py repositories/students.py models/search_filters.py >/dev/null
uv run python scripts/benchmark_students_search.py
