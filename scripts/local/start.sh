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
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}"
RABBITMQ_QUEUE_TYPE="${RABBITMQ_QUEUE_TYPE:-classic}"
MODEL_DIR="${MODEL_DIR:-$ROOT_DIR/.local/models}"
mkdir -p "$MODEL_DIR"

start_backend() {
  local name="$1"
  local service_dir="$2"
  local port="$3"
  shift 3

  local log_file="$LOG_DIR/${name}.log"
  local pid_file="$PID_DIR/${name}.pid"

  (
    cd "$service_dir"
    nohup env \
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
      RABBITMQ_QUEUE_TYPE="$RABBITMQ_QUEUE_TYPE" \
      CORS_ALLOW_ORIGINS="$CORS_ALLOW_ORIGINS" \
      "$@" \
      uvicorn app.main:app --host 0.0.0.0 --port "$port" >>"$log_file" 2>&1 &
    echo $! >"$pid_file"
  )
}

start_frontend() {
  local log_file="$LOG_DIR/dashboard.log"
  local pid_file="$PID_DIR/dashboard.pid"

  (
    cd "$ROOT_DIR/frontend/dashboard"
    nohup env \
      VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:8000}" \
      VITE_WS_BASE_URL="${VITE_WS_BASE_URL:-http://localhost:8020}" \
      npm run dev >>"$log_file" 2>&1 &
    echo $! >"$pid_file"
  )
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

echo "Starting backend services..."
start_backend "ml-inference" "$ROOT_DIR/backend/services/ml_inference" "8001" "MODEL_DIR=$MODEL_DIR"
start_backend "feature-enrichment" "$ROOT_DIR/backend/services/feature_enrichment" "8040"
start_backend "data-connector" "$ROOT_DIR/backend/services/data_connector" "8030"
start_backend "metrics-aggregator" "$ROOT_DIR/backend/services/metrics_aggregator" "8050"
start_backend "api-gateway" "$ROOT_DIR/backend/services/api_gateway" "8000"
start_backend "event-worker" "$ROOT_DIR/backend/services/event_worker" "8010" "MAX_EVENT_RETRIES=3"
start_backend "notification-service" "$ROOT_DIR/backend/services/notification_service" "8020"

echo "Starting frontend dashboard..."
start_frontend

echo "Waiting for service health checks..."
wait_for_url "http://localhost:8001/health/live" "ML Inference"
wait_for_url "http://localhost:8040/health/live" "Feature Enrichment"
wait_for_url "http://localhost:8030/health/live" "Data Connector"
wait_for_url "http://localhost:8050/health/live" "Metrics Aggregator"
wait_for_url "http://localhost:8000/health/live" "API Gateway"
wait_for_url "http://localhost:8010/health/live" "Event Worker"
wait_for_url "http://localhost:8020/health/live" "Notification Service"
wait_for_url "http://localhost:5173" "Dashboard" 120

echo
echo "Local dev stack is running."
echo "Dashboard: http://localhost:5173"
echo "API Docs:  http://localhost:8000/docs"
echo "Connectors: http://localhost:8030/v1/connectors/status"
echo "Enrichment: http://localhost:8040/health/live"
echo "Metrics:    http://localhost:8050/health/live"
echo "RabbitMQ:  http://localhost:15672"
echo "Logs:      $LOG_DIR"
echo "Stop:      ./scripts/local/stop.sh"
