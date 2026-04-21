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

RUN_UV="$UV_BIN"
if ! "$RUN_UV" --version >/dev/null 2>&1; then
  RUN_UV="$(command -v uv || true)"
fi
if [ -z "$RUN_UV" ]; then
  echo "uv executable not available" >&2
  exit 127
fi

PYTHONPATH=. "$RUN_UV" run python -m py_compile \
  repositories/base.py \
  repositories/admin.py \
  repositories/users.py \
  repositories/students.py \
  scripts/benchmark_db_layer.py >/dev/null

PYTHONPATH=. "$RUN_UV" run python -m scripts.benchmark_db_layer
