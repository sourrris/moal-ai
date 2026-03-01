#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it first: https://brew.sh/" >&2
  exit 1
fi

FORMULAE=(python@3.11 postgresql@16 redis rabbitmq nginx)
MISSING=()
for formula in "${FORMULAE[@]}"; do
  if ! brew list --versions "$formula" >/dev/null 2>&1; then
    MISSING+=("$formula")
  fi
done

if [[ "${#MISSING[@]}" -gt 0 ]]; then
  echo "Installing missing Homebrew formulae: ${MISSING[*]}"
  brew install "${MISSING[@]}"
else
  echo "All required Homebrew formulae are already installed."
fi

echo "Starting local infrastructure services..."
brew services start postgresql@16 >/dev/null
brew services start redis >/dev/null
brew services start rabbitmq >/dev/null

PG_PREFIX="$(brew --prefix postgresql@16)"
PSQL="$PG_PREFIX/bin/psql"

echo "Initializing PostgreSQL role/database/schema..."
"$PSQL" -d postgres -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='risk') THEN CREATE ROLE risk LOGIN PASSWORD 'risk'; ELSE ALTER ROLE risk LOGIN PASSWORD 'risk'; END IF; END \$\$;"
if [[ "$("$PSQL" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='risk_monitor'")" != "1" ]]; then
  "$PSQL" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE risk_monitor OWNER risk;"
fi
"$PSQL" -d risk_monitor -v ON_ERROR_STOP=1 -f "$ROOT_DIR/infra/postgres/init/001_schema.sql" >/dev/null
"$PSQL" -d risk_monitor -v ON_ERROR_STOP=1 -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO risk; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO risk; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO risk; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO risk;" >/dev/null

PYTHON_BIN="$(brew --prefix)/bin/python3.11"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(brew --prefix python@3.11)/bin/python3.11"
fi

echo "Setting up Python virtual environment..."
"$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
# Ensure pip is available (Homebrew Python venvs sometimes omit it)
"$ROOT_DIR/.venv/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
# shellcheck disable=SC1091
source "$ROOT_DIR/.venv/bin/activate"

PIP="$ROOT_DIR/.venv/bin/pip"
"$PIP" install --upgrade pip >/dev/null
"$PIP" install -e "$ROOT_DIR/backend/libs/common" >/dev/null
"$PIP" install -r "$ROOT_DIR/backend/services/risk/api/requirements.txt" >/dev/null
"$PIP" install -r "$ROOT_DIR/backend/services/risk/worker/requirements.txt" >/dev/null
"$PIP" install -r "$ROOT_DIR/backend/services/risk/ml/requirements.txt" >/dev/null
"$PIP" install -r "$ROOT_DIR/backend/services/risk/notification/requirements.txt" >/dev/null
"$PIP" install -r "$ROOT_DIR/backend/services/risk/connector/requirements.txt" >/dev/null
"$PIP" install -r "$ROOT_DIR/backend/services/risk/metrics/requirements.txt" >/dev/null
"$PIP" install -r "$ROOT_DIR/backend/services/risk/enrichment/requirements.txt" >/dev/null
"$PIP" install alembic >/dev/null
"$PIP" install greenlet >/dev/null

echo "Applying Alembic migrations..."
(cd "$ROOT_DIR/backend" && DATABASE_URL="postgresql+asyncpg://risk:risk@localhost:5432/risk_monitor" "$ROOT_DIR/.venv/bin/alembic" -c alembic.ini upgrade head >/dev/null)

echo "Installing frontend dependencies..."
(cd "$ROOT_DIR/frontend/dashboard" && npm install)

cat > "$ROOT_DIR/frontend/dashboard/.env.local" <<'EOF'
VITE_API_BASE_URL=http://api.localhost
VITE_WS_BASE_URL=http://ws.localhost
EOF

echo
echo "Local setup complete."
echo "Next: ./scripts/local/start.sh"
