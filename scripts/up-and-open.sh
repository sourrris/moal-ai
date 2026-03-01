#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

LOCAL_APP_DOMAIN="${LOCAL_APP_DOMAIN:-app.localhost}"
LOCAL_API_DOMAIN="${LOCAL_API_DOMAIN:-api.localhost}"
LOCAL_WS_DOMAIN="${LOCAL_WS_DOMAIN:-ws.localhost}"

if [[ "$LOCAL_APP_DOMAIN" == "app.aegis.test" && "$LOCAL_API_DOMAIN" == "api.aegis.test" && "$LOCAL_WS_DOMAIN" == "ws.aegis.test" ]]; then
  echo "Detected legacy *.aegis.test defaults in environment. Using *.localhost for local routing."
  LOCAL_APP_DOMAIN="app.localhost"
  LOCAL_API_DOMAIN="api.localhost"
  LOCAL_WS_DOMAIN="ws.localhost"
fi
export LOCAL_APP_DOMAIN LOCAL_API_DOMAIN LOCAL_WS_DOMAIN

is_localhost_domain() {
  local domain="$1"
  [[ "$domain" == "localhost" || "$domain" == *.localhost ]]
}

ensure_hosts_entry() {
  local domains=("$LOCAL_APP_DOMAIN" "$LOCAL_API_DOMAIN" "$LOCAL_WS_DOMAIN")
  local has_custom_domain=0

  for domain in "${domains[@]}"; do
    if ! is_localhost_domain "$domain"; then
      has_custom_domain=1
      break
    fi
  done

  if [[ "$has_custom_domain" -eq 0 ]]; then
    return
  fi

  for domain in "${domains[@]}"; do
    if is_localhost_domain "$domain"; then
      continue
    fi
    local escaped_domain
    escaped_domain="${domain//./\\.}"
    if ! grep -Eq "(^|[[:space:]])${escaped_domain}($|[[:space:]])" /etc/hosts; then
      echo "Local domains are missing in /etc/hosts. Running setup script..."
      ./scripts/setup-local-domains.sh
      return
    fi
  done
}

ensure_hosts_entry

APP_URL="http://${LOCAL_APP_DOMAIN}"
API_URL="http://${LOCAL_API_DOMAIN}"
WS_STATUS_URL="http://${LOCAL_WS_DOMAIN}/v1/notifications/connections"
RABBITMQ_URL="http://localhost:15672"
CONNECTOR_URL="http://localhost:8030/v1/connectors/status"
ENRICHMENT_URL="http://localhost:8040/health/live"
METRICS_URL="http://localhost:8050/health/live"

wait_for_url() {
  local url="$1"
  local name="$2"
  local timeout_seconds="${3:-180}"
  local elapsed=0

  until curl --noproxy '*' -fsS "$url" >/dev/null 2>&1; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [[ "$elapsed" -ge "$timeout_seconds" ]]; then
      echo "Timed out waiting for ${name} at ${url}" >&2
      return 1
    fi
  done

  echo "Ready: ${name} (${url})"
}

open_url() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  else
    echo "Open manually: $url"
  fi
}

echo "Starting services with build..."
docker compose up -d --build

echo "Waiting for endpoints..."
failures=0
if ! wait_for_url "$APP_URL" "Dashboard"; then
  failures=$((failures + 1))
fi
if ! wait_for_url "$API_URL/health/live" "API Gateway health"; then
  failures=$((failures + 1))
fi
if ! wait_for_url "$WS_STATUS_URL" "Notification service"; then
  failures=$((failures + 1))
fi
if ! wait_for_url "$RABBITMQ_URL" "RabbitMQ UI"; then
  failures=$((failures + 1))
fi
if ! wait_for_url "$CONNECTOR_URL" "Data connector"; then
  failures=$((failures + 1))
fi
if ! wait_for_url "$ENRICHMENT_URL" "Feature enrichment"; then
  failures=$((failures + 1))
fi
if ! wait_for_url "$METRICS_URL" "Metrics aggregator"; then
  failures=$((failures + 1))
fi

echo "Opening browser tabs..."
open_url "$APP_URL"
open_url "$API_URL/docs"
open_url "$WS_STATUS_URL"
open_url "$RABBITMQ_URL"
open_url "$CONNECTOR_URL"

if [[ "$failures" -gt 0 ]]; then
  echo
  echo "Some endpoints were not reachable during startup checks."
  echo "Quick diagnostics:"
  docker compose ps
  docker compose logs --tail=60 local-gateway dashboard api-gateway notification-service
else
  echo "All URLs opened."
fi
