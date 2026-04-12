#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Missing Python virtual environment. Run ./scripts/local/setup.sh first." >&2
  exit 1
fi

exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/backend/scripts/seed_demo_stream.py" "$@"
