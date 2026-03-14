#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  echo "Missing Python virtual environment. Run ./scripts/local/setup.sh first." >&2
  exit 1
fi

RUN_DIR="$ROOT_DIR/.local/run"
LOG_DIR="$RUN_DIR/logs"
PID_DIR="$RUN_DIR/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

"$ROOT_DIR/scripts/local/stop.sh" >/dev/null 2>&1 || true

# shellcheck disable=SC1091
source "$ROOT_DIR/.venv/bin/activate"

POSTGRES_DSN="${POSTGRES_DSN:-postgresql+asyncpg://risk:risk@localhost:5432/risk_monitor}"
RABBITMQ_URL="${RABBITMQ_URL:-amqp://guest:guest@localhost:5672/}"
REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:-change-me-in-prod}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
ML_INFERENCE_URL="${ML_INFERENCE_URL:-http://localhost:8001}"
FEATURE_ENRICHMENT_URL="${FEATURE_ENRICHMENT_URL:-http://localhost:8040}"
DATA_CONNECTOR_URL="${DATA_CONNECTOR_URL:-http://localhost:8030}"
API_GATEWAY_URL="${API_GATEWAY_URL:-http://localhost:8000}"
CONTROL_API_URL="${CONTROL_API_URL:-http://localhost:8060}"
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-http://app.localhost,http://control.localhost,http://ops-control.localhost,http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:5175}"
AUTH_COOKIE_DOMAIN="${AUTH_COOKIE_DOMAIN:-localhost}"
RABBITMQ_QUEUE_TYPE="${RABBITMQ_QUEUE_TYPE:-classic}"
MODEL_DIR="${MODEL_DIR:-$ROOT_DIR/.local/models}"
mkdir -p "$MODEL_DIR"

apply_migrations() {
  echo "Applying Alembic migrations..."
  (
    cd "$ROOT_DIR/backend"
    DATABASE_URL="$POSTGRES_DSN" "$ROOT_DIR/.venv/bin/alembic" -c alembic.ini upgrade head >/dev/null
  )
}

maintain_partitions() {
  echo "Ensuring events_v2 partitions..."
  "$ROOT_DIR/scripts/local/maintain-partitions.sh" || {
    echo "WARNING: Failed to ensure events_v2 partitions. v2 event ingest may fail." >&2
  }
}

apply_migrations
maintain_partitions

start_detached() {
  local work_dir="$1"
  local log_file="$2"
  local pid_file="$3"
  shift 3

  "$ROOT_DIR/.venv/bin/python" - "$work_dir" "$log_file" "$pid_file" "$@" <<'PY'
import subprocess
import sys
from pathlib import Path

work_dir, log_file, pid_file, *command = sys.argv[1:]

log_path = Path(log_file)
pid_path = Path(pid_file)

with log_path.open("ab", buffering=0) as log_handle:
    process = subprocess.Popen(
        command,
        cwd=work_dir,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )

pid_path.write_text(f"{process.pid}\n", encoding="utf-8")
PY
}

assert_pid_running() {
  local pid_file="$1"
  local name="$2"
  local log_file="$3"
  local pid
  pid="$(cat "$pid_file")"

  if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "${name} exited unexpectedly. Recent logs:" >&2
    tail -n 40 "$log_file" >&2 || true
    return 1
  fi
}

verify_started_processes() {
  local pid_file
  for pid_file in "$PID_DIR"/*.pid; do
    [[ -f "$pid_file" ]] || continue
    local name
    name="$(basename "$pid_file" .pid)"
    assert_pid_running "$pid_file" "$name" "$LOG_DIR/${name}.log" || return 1
  done
}

start_backend() {
  local name="$1"
  local service_dir="$2"
  local port="$3"
  shift 3

  local log_file="$LOG_DIR/${name}.log"
  local pid_file="$PID_DIR/${name}.pid"
  : >"$log_file"
  rm -f "$pid_file"

  start_detached \
    "$service_dir" \
    "$log_file" \
    "$pid_file" \
    env \
    SERVICE_NAME="$name" \
    API_PORT="$port" \
    LOG_LEVEL="$LOG_LEVEL" \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    POSTGRES_DSN="$POSTGRES_DSN" \
    RABBITMQ_URL="$RABBITMQ_URL" \
    REDIS_URL="$REDIS_URL" \
    ML_INFERENCE_URL="$ML_INFERENCE_URL" \
    FEATURE_ENRICHMENT_URL="$FEATURE_ENRICHMENT_URL" \
    DATA_CONNECTOR_URL="$DATA_CONNECTOR_URL" \
    API_GATEWAY_URL="$API_GATEWAY_URL" \
    CONTROL_API_URL="$CONTROL_API_URL" \
    RABBITMQ_QUEUE_TYPE="$RABBITMQ_QUEUE_TYPE" \
    CORS_ALLOW_ORIGINS="$CORS_ALLOW_ORIGINS" \
    AUTH_COOKIE_DOMAIN="$AUTH_COOKIE_DOMAIN" \
    "$@" \
    uvicorn app.main:app --host 0.0.0.0 --port "$port"
}

start_frontend_app() {
  local name="$1"
  local app_dir="$2"
  local port="$3"
  local api_base="$4"
  local ws_base="$5"
  local monitoring_url="$6"
  local control_api_base="$7"
  local monitoring_api_base="${8:-}"
  local log_file="$LOG_DIR/${name}.log"
  local pid_file="$PID_DIR/${name}.pid"
  : >"$log_file"
  rm -f "$pid_file"

  start_detached \
    "$app_dir" \
    "$log_file" \
    "$pid_file" \
    env \
    PORT="$port" \
    VITE_API_BASE_URL="$api_base" \
    VITE_WS_BASE_URL="$ws_base" \
    VITE_MONITORING_APP_URL="$monitoring_url" \
    VITE_CONTROL_API_BASE_URL="$control_api_base" \
    VITE_MONITORING_API_BASE_URL="$monitoring_api_base" \
    MONITORING_API_PROXY_TARGET="$API_GATEWAY_URL" \
    npm run dev
}

wait_for_url() {
  local url="$1"
  local name="$2"
  local timeout_seconds="${3:-90}"
  local elapsed=0

  until curl -fsS "$url" >/dev/null 2>&1; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [[ "$elapsed" -ge "$timeout_seconds" ]]; then
      echo "Timed out waiting for ${name} (${url}). Check logs in $LOG_DIR" >&2
      return 1
    fi
  done

  echo "Ready: ${name} (${url})"
}

ensure_port_free() {
  local port="$1"
  local name="$2"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port ${port} is already in use; cannot start ${name}. Stop the conflicting process and retry." >&2
    return 1
  fi
}

ensure_frontend_dependencies() {
  local app_dir="$1"
  if [[ ! -d "$app_dir/node_modules" ]]; then
    echo "Frontend dependencies missing. Installing in $app_dir..."
    (cd "$app_dir" && npm install)
    return 0
  fi

  if ! (cd "$app_dir" && node -e "require.resolve('vite/package.json')" >/dev/null 2>&1); then
    echo "Frontend dependencies are out of sync with package.json. Reinstalling..."
    (cd "$app_dir" && npm install)
  fi
}

echo "Starting foundational backend services..."
start_backend "ml-inference" "$ROOT_DIR/backend/services/risk/ml" "8001" "MODEL_DIR=$MODEL_DIR"
start_backend "feature-enrichment" "$ROOT_DIR/backend/services/risk/enrichment" "8040"
start_backend "metrics-aggregator" "$ROOT_DIR/backend/services/risk/metrics" "8050"
wait_for_url "http://localhost:8001/health/live" "ML Inference"
wait_for_url "http://localhost:8040/health/live" "Feature Enrichment"
wait_for_url "http://localhost:8050/health/live" "Metrics Aggregator"

echo "Starting API, worker, and notification services..."
start_backend "api-gateway" "$ROOT_DIR/backend/services/risk/api" "8000"
start_backend "event-worker" "$ROOT_DIR/backend/services/risk/worker" "8010" "MAX_EVENT_RETRIES=3"
start_backend "notification-service" "$ROOT_DIR/backend/services/risk/notification" "8020"
wait_for_url "http://localhost:8000/health/live" "API Gateway"
wait_for_url "http://localhost:8010/health/live" "Event Worker"
wait_for_url "http://localhost:8020/health/live" "Notification Service"

echo "Starting data connector..."
start_backend "data-connector" "$ROOT_DIR/backend/services/risk/connector" "8030"
wait_for_url "http://localhost:8030/health/live" "Data Connector"

echo "Starting control services..."
start_backend "control-api" "$ROOT_DIR/backend/services/risk/control_plane" "8060"
start_backend "alert-router" "$ROOT_DIR/backend/services/risk/alert_router" "8061"
wait_for_url "http://localhost:8060/health/live" "Control API"
wait_for_url "http://localhost:8061/health/live" "Alert Router"

echo "Starting frontend apps..."
ensure_frontend_dependencies "$ROOT_DIR/frontend/dashboard"
ensure_frontend_dependencies "$ROOT_DIR/frontend/control-tenant"
ensure_frontend_dependencies "$ROOT_DIR/frontend/control-ops"
ensure_port_free "5173" "dashboard"
ensure_port_free "5174" "control-tenant"
ensure_port_free "5175" "control-ops"
start_frontend_app "dashboard" "$ROOT_DIR/frontend/dashboard" "5173" "http://api.localhost" "http://ws.localhost" "http://app.localhost" "http://control-api.localhost"
start_frontend_app "control-tenant" "$ROOT_DIR/frontend/control-tenant" "5174" "http://api.localhost" "http://ws.localhost" "http://app.localhost" "http://control-api.localhost" "/monitoring-api"
start_frontend_app "control-ops" "$ROOT_DIR/frontend/control-ops" "5175" "http://api.localhost" "http://ws.localhost" "http://app.localhost" "http://control-api.localhost" "/monitoring-api"
wait_for_url "http://localhost:5173" "Dashboard" 120
wait_for_url "http://localhost:5174" "Control Tenant Console" 120
wait_for_url "http://localhost:5175" "Control Ops Console" 120

# ── Start nginx reverse proxy ───────────────────────────────────
NGINX_CONF="$ROOT_DIR/infra/reverse-proxy/nginx-local.conf"
echo "Starting nginx reverse proxy..."
if command -v nginx >/dev/null 2>&1; then
  # Stop any previous nginx using our config
  nginx -c "$NGINX_CONF" -s stop >/dev/null 2>&1 || true
  sleep 0.5
  nginx -c "$NGINX_CONF"
  echo "Ready: nginx (http://app.localhost)"
else
  echo "WARNING: nginx not found. Install with: brew install nginx" >&2
  echo "         Falling back to direct localhost ports." >&2
fi

verify_started_processes

echo
echo "Local dev stack is running."
echo "Release smoke: use docker compose up -d --build"
echo "Dashboard:  http://app.localhost"
echo "Control:    http://control.localhost"
echo "Ops:        http://ops-control.localhost"
echo "API Docs:   http://api.localhost/docs"
echo "Control API:http://control-api.localhost/docs"
echo "WebSocket:  http://ws.localhost"
echo "Connectors: http://localhost:8030/v1/connectors/status"
echo "Enrichment: http://localhost:8040/health/live"
echo "Metrics:    http://localhost:8050/health/live"
echo "RabbitMQ:   http://localhost:15672"
echo "Logs:       $LOG_DIR"
echo "Stop:       ./scripts/local/stop.sh"
