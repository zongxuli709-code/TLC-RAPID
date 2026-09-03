#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.12, then try again."
  exit 1
fi

exec "$PYTHON_BIN" run_analysis.py

