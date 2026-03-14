#!/usr/bin/env bash
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://risk:risk@localhost:5432/risk_monitor}"
USERNAME="${ADMIN_USERNAME:-admin}"
PASSWORD="${ADMIN_PASSWORD:-$(openssl rand -base64 24)}"

psql "$DB_URL" <<SQL
INSERT INTO users (username, password_hash, role)
VALUES ('$USERNAME', crypt('$PASSWORD', gen_salt('bf')), 'admin')
ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash;
SQL

echo "Admin user '$USERNAME' created. Password: $PASSWORD"
echo "Store this password securely — it will not be shown again."
