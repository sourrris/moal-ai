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
JWT_SECRET_KEY="${JWT_SECRET_KEY:-change-me-in-prod}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
ML_INFERENCE_URL="${ML_INFERENCE_URL:-http://localhost:8001}"
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}"
MODEL_DIR="${MODEL_DIR:-$ROOT_DIR/.local/models}"
mkdir -p "$MODEL_DIR"

apply_migrations() {
  echo "Applying Alembic migrations..."
  (
    cd "$ROOT_DIR/backend"
    DATABASE_URL="$POSTGRES_DSN" "$ROOT_DIR/.venv/bin/alembic" -c alembic.ini upgrade head >/dev/null
  )
}

apply_migrations

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
    echo "Port ${port} is already in use; cannot start ${name}." >&2
    return 1
  fi
}

ensure_frontend_dependencies() {
  local app_dir="$1"
  if [[ ! -d "$app_dir/node_modules" ]]; then
    echo "Frontend dependencies missing. Installing in $app_dir..."
    (cd "$app_dir" && npm install)
  fi
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
    ML_INFERENCE_URL="$ML_INFERENCE_URL" \
    CORS_ALLOW_ORIGINS="$CORS_ALLOW_ORIGINS" \
    "$@" \
    uvicorn app.main:app --host 0.0.0.0 --port "$port" --reload
}

echo "Starting backend services..."
start_backend "ml" "$ROOT_DIR/backend/services/risk/ml" "8001" "MODEL_DIR=$MODEL_DIR"
wait_for_url "http://localhost:8001/health/live" "ML Service"

start_backend "api" "$ROOT_DIR/backend/services/risk/api" "8000"
wait_for_url "http://localhost:8000/health/live" "API"

echo "Starting dashboard..."
ensure_frontend_dependencies "$ROOT_DIR/frontend/dashboard"
ensure_port_free "5173" "dashboard"

local_log="$LOG_DIR/dashboard.log"
local_pid="$PID_DIR/dashboard.pid"
: >"$local_log"
rm -f "$local_pid"

start_detached \
  "$ROOT_DIR/frontend/dashboard" \
  "$local_log" \
  "$local_pid" \
  env \
  PORT="5173" \
  VITE_API_BASE_URL="http://localhost:8000" \
  npm run dev

wait_for_url "http://localhost:5173" "Dashboard" 120

echo
echo "moal-ai local dev stack is running."
echo "Dashboard:  http://localhost:5173"
echo "API Docs:   http://localhost:8000/docs"
echo "ML Service: http://localhost:8001/docs"
echo "Logs:       $LOG_DIR"
echo "Stop:       ./scripts/local/stop.sh"
