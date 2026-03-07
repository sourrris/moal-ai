#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

MATCHES="$(rg -n "^\s*(from|import)\s+aegis_connectors\b" backend || true)"
if [[ -n "$MATCHES" ]]; then
  echo "Core import isolation failed. Found direct imports from aegis_connectors in backend:"
  echo "$MATCHES"
  exit 1
fi

echo "Core import isolation check passed."
