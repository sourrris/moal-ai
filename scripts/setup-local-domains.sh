#!/usr/bin/env bash
set -euo pipefail

HOSTS_FILE="/etc/hosts"
LOCAL_APP_DOMAIN="${LOCAL_APP_DOMAIN:-app.localhost}"
LOCAL_API_DOMAIN="${LOCAL_API_DOMAIN:-api.localhost}"
LOCAL_WS_DOMAIN="${LOCAL_WS_DOMAIN:-ws.localhost}"
LOCAL_CONTROL_DOMAIN="${LOCAL_CONTROL_DOMAIN:-control.localhost}"
LOCAL_OPS_CONTROL_DOMAIN="${LOCAL_OPS_CONTROL_DOMAIN:-ops-control.localhost}"
LOCAL_CONTROL_API_DOMAIN="${LOCAL_CONTROL_API_DOMAIN:-control-api.localhost}"

is_localhost_domain() {
  local domain="$1"
  [[ "$domain" == "localhost" || "$domain" == *.localhost ]]
}

domains=(
  "$LOCAL_APP_DOMAIN"
  "$LOCAL_API_DOMAIN"
  "$LOCAL_WS_DOMAIN"
  "$LOCAL_CONTROL_DOMAIN"
  "$LOCAL_OPS_CONTROL_DOMAIN"
  "$LOCAL_CONTROL_API_DOMAIN"
)
missing_domains=()

for domain in "${domains[@]}"; do
  if is_localhost_domain "$domain"; then
    continue
  fi

  escaped_domain="${domain//./\\.}"
  if ! grep -Eq "(^|[[:space:]])${escaped_domain}($|[[:space:]])" "$HOSTS_FILE"; then
    missing_domains+=("$domain")
  fi
done

if [[ "${#missing_domains[@]}" -eq 0 ]]; then
  echo "No /etc/hosts update required."
  exit 0
fi

line="127.0.0.1 ${missing_domains[*]}"
echo "$line" | sudo tee -a "$HOSTS_FILE" >/dev/null

echo "Added local domains: ${missing_domains[*]}"
