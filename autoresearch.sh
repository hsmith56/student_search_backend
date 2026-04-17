#!/usr/bin/env bash
set -euo pipefail

UV_ROOT="/tmp/pi-autoresearch-uv"
UV_BIN="$UV_ROOT/uv"
if [ ! -x "$UV_BIN" ]; then
  rm -rf "$UV_ROOT"
  mkdir -p "$UV_ROOT"
  curl -Lsf -o "$UV_ROOT/uv.tar.gz" "https://github.com/astral-sh/uv/releases/download/0.11.7/uv-x86_64-unknown-linux-gnu.tar.gz"
  tar -xzf "$UV_ROOT/uv.tar.gz" -C "$UV_ROOT"
  mv "$UV_ROOT"/uv-x86_64-unknown-linux-gnu/uv "$UV_BIN"
  chmod +x "$UV_BIN"
fi

export UV_PROJECT_ENVIRONMENT="/tmp/pi-autoresearch-venv"
export UV_LINK_MODE="copy"

PYTHONPATH=. "$UV_BIN" run python -m py_compile routers/students.py utils/search_filters.py repositories/students.py models/search_filters.py >/dev/null
PYTHONPATH=. "$UV_BIN" run python -m scripts.benchmark_students_search
