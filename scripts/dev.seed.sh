#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-risk}"
PG_PASSWORD="${PG_PASSWORD:-risk}"
PG_DATABASE="${PG_DATABASE:-risk_monitor}"

if command -v /opt/homebrew/opt/postgresql@16/bin/psql >/dev/null 2>&1; then
  PSQL="/opt/homebrew/opt/postgresql@16/bin/psql"
elif command -v psql >/dev/null 2>&1; then
  PSQL="$(command -v psql)"
else
  echo "psql is required for seeding." >&2
  exit 1
fi

PGPASSWORD="$PG_PASSWORD" "$PSQL" \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d "$PG_DATABASE" \
  -v ON_ERROR_STOP=1 \
  -f "$ROOT_DIR/infra/postgres/init/001_schema.sql"

echo "Seed complete for $PG_DATABASE on $PG_HOST:$PG_PORT"
