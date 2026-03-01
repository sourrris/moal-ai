#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PGHOST="${PGHOST:-localhost}"
PGUSER="${PGUSER:-risk}"
PGDATABASE="${PGDATABASE:-risk_monitor}"
PGPASSWORD="${PGPASSWORD:-risk}"

FUTURE_DAYS="${FUTURE_DAYS:-14}"

/bin/zsh -lc "PGPASSWORD=${PGPASSWORD} /opt/homebrew/opt/postgresql@16/bin/psql -h ${PGHOST} -U ${PGUSER} -d ${PGDATABASE} -c \"SELECT ensure_events_v2_daily_partitions(CURRENT_DATE, CURRENT_DATE + ${FUTURE_DAYS}, 8);\""

echo "Ensured events_v2 partitions through +${FUTURE_DAYS} days."
