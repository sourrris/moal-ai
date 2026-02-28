# Real-Time AI Risk Monitoring System

Production-grade distributed scaffold for real-time AI risk monitoring with FastAPI microservices, RabbitMQ event routing, Redis Pub/Sub WebSocket streaming, PostgreSQL persistence, TensorFlow anomaly detection, and React dashboard.

## Stack
- Backend: Python 3.11+, FastAPI, PostgreSQL, RabbitMQ, Redis, TensorFlow
- Frontend: React + TypeScript + Recharts + WebSocket client
- Infra: Docker + Docker Compose (optional), or native local services via Homebrew

## Services
- API Gateway: Auth, ingestion, model management proxy
- Event Worker: Consumes events, calls ML inference, persists results, emits alerts
- ML Inference: TensorFlow autoencoder train/infer + model version activation
- Notification Service: Rabbit alert consumer + Redis Pub/Sub + WebSocket fan-out
- Data Connector Service: Scheduled internet feed ingestion (OFAC/FATF/OpenSanctions/FX)
- Feature Enrichment Service: Risk-context enrichment lookups from cached reference data
- Metrics Aggregator Service: Continuous 1m/1h metrics rollups + live metrics stream
- Dashboard: React live monitoring UI

## Local Development (No Docker)
1. Run one-time setup (installs/starts PostgreSQL, Redis, RabbitMQ; creates `.venv`; installs backend + frontend dependencies):

```bash
./scripts/local/setup.sh
```

2. Start all backend services and dashboard:

```bash
./scripts/local/start.sh
```

3. Stop local app processes:

```bash
./scripts/local/stop.sh
```

5. Optional operational helpers:

```bash
# Ensure events_v2 partitions for the next 14 days
./scripts/local/maintain-partitions.sh

# Replay dead-lettered events back to events exchange
./scripts/local/replay-dlq.sh --limit 50
```

4. URLs:
   - Dashboard `http://localhost:5173`
   - API docs `http://localhost:8000/docs`
   - Data connector status `http://localhost:8030/v1/connectors/status`
   - Data connector runs `http://localhost:8030/v1/connectors/runs`
   - Data connector errors `http://localhost:8030/v1/connectors/errors`
   - Feature enrichment health `http://localhost:8040/health/live`
   - Metrics aggregator health `http://localhost:8050/health/live`
   - Notification status `http://localhost:8020/v1/notifications/connections`
   - RabbitMQ UI `http://localhost:15672`

## Docker Quick Start
1. Copy `.env.example` to `.env` and set secrets.
2. Start services and auto-open local URLs in browser tabs:

```bash
./scripts/up-and-open.sh
```

3. Optional: if you override domains to non-`*.localhost` values in `.env`, add host mappings once:

```bash
./scripts/setup-local-domains.sh
```

4. The script opens:
   - Dashboard `http://app.localhost`
   - API docs `http://api.localhost/docs`
   - Notification status `http://ws.localhost/v1/notifications/connections`
   - RabbitMQ `http://localhost:15672` (`guest/guest`)

## Codex Web Environment
Use this when you want to continue working from any device in `chatgpt.com/codex`.

1. Open Codex and connect this GitHub repository.
2. Create an environment for this repo/branch.
3. Set runtimes:
   - Python `3.11` (or `3.12`)
   - Node.js `20`
4. Add environment variables/secrets from `.env.example`.
5. Use this setup script:

```bash
set -euo pipefail
python -m pip install --upgrade pip
python -m pip install -e backend/libs/common
python -m pip install -r backend/services/api_gateway/requirements.txt
python -m pip install -r backend/services/event_worker/requirements.txt
python -m pip install -r backend/services/ml_inference/requirements.txt
python -m pip install -r backend/services/notification_service/requirements.txt
python -m pip install -r backend/services/data_connector/requirements.txt
python -m pip install -r backend/services/feature_enrichment/requirements.txt
python -m pip install -r backend/services/metrics_aggregator/requirements.txt
npm ci --prefix frontend/dashboard
```

6. Start the stack inside Codex Web with:

```bash
docker compose up -d --build
```

## Default Demo Credentials
- username: `admin`
- password: `admin123`

## Docs
- Architecture and diagrams: `docs/architecture.md`
- Folder structure: `docs/folder-structure.md`
- V2 operationalization guide: `docs/v2-operationalization.md`

## Key Production Patterns Included
- Event-driven microservices via RabbitMQ
- Redis Pub/Sub-based real-time streaming
- JWT authentication
- JWT v2 tenant-aware claims + refresh token flow (`/v2/auth/token`, `/v2/auth/refresh`)
- Idempotent ingestion and processing controls
- Retry + dead-letter queue handling
- Structured JSON logging
- Health checks for orchestration

## V2 Operational APIs
- `POST /v2/events/ingest`
- `POST /v2/events/ingest/batch`
- `GET /v2/alerts`
- `POST /v2/alerts/{alert_id}/ack`
- `POST /v2/alerts/{alert_id}/resolve`
- `GET /v2/risk-decisions/{event_id}`
- `GET /v2/data-sources/status`
- `GET /v2/data-sources/runs`

Connector control endpoints:
- `POST /v1/connectors/run-now?source_name=...`
- `POST /v1/connectors/enable?source_name=...`
- `POST /v1/connectors/disable?source_name=...`
- `GET /v1/connectors/lookup/ip?ip=...`
- `GET /v1/connectors/lookup/bin?card_bin=...`
- `GET /v2/models/drift`
- `GET /v2/models/training-runs`

## CI Baseline (PR1)
- GitHub Actions workflow: `.github/workflows/ci.yml`
- Backend checks: Ruff lint, mypy smoke type-check, pytest smoke tests
- Frontend checks: Vitest + TypeScript build
- Container sanity: Docker build matrix for all service Dockerfiles

Dependency and security posture notes are tracked in `docs/audit/pr1-audit-ci-baseline.md`.

## Backend Env Var Compatibility
Backend services now accept standardized env names in addition to legacy names:
- `DATABASE_URL` (maps to Postgres DSN)
- `REDIS_URL`
- `RABBITMQ_URL`
- `JWT_SECRET`

This keeps rollout backward-compatible while we migrate to production secret conventions.


## Production Upgrade Plan
A detailed incremental hardening roadmap is tracked in `docs/production-upgrade-plan.md`.

Recent hardening updates include:
- Backward-compatible env standardization support (`DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, `JWT_SECRET`).
- Auth password verification with opportunistic hash upgrades toward argon2.
- Secure default admin seed hash generation using PostgreSQL `pgcrypto` (`crypt` + `gen_salt`).


## Social Sign-In (Google / Apple)
The API gateway now exposes OAuth start/callback endpoints for social login:
- `GET /v1/auth/google/login`
- `GET /v1/auth/apple/login`

Set OAuth credentials in `.env`:
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`
- `APPLE_OAUTH_CLIENT_ID`, `APPLE_OAUTH_CLIENT_SECRET`, `APPLE_OAUTH_REDIRECT_URI`
- `FRONTEND_BASE_URL` (used for post-login redirect to `/auth/callback`)
