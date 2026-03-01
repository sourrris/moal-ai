#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

"$ROOT_DIR/scripts/local/stop.sh" || true
"$ROOT_DIR/scripts/local/setup.sh"
"$ROOT_DIR/scripts/dev.seed.sh"
