# Engineering Refactor Diff Summary

## Overview
Structural modernization completed with behavior-preserving intent across backend services, frontend feature modules, tests, docs, scripts, Docker references, and CI references.

## Major Structural Changes

- Renamed backend service directories to domain-driven structure under `backend/services/risk/*`:
  - `api_gateway` -> `risk/api`
  - `event_worker` -> `risk/worker`
  - `ml_inference` -> `risk/ml`
  - `notification_service` -> `risk/notification`
  - `data_connector` -> `risk/connector`
  - `feature_enrichment` -> `risk/enrichment`
  - `metrics_aggregator` -> `risk/metrics`
- Renamed high-churn generic backend modules to intent-based names:
  - `services.py` -> `risk_event_service.py`
  - `service.py` -> `feature_enrichment_service.py`, `model_inference_service.py`
  - `routes.py` -> `connector_routes.py`, `enrichment_routes.py`, `model_routes.py`, `notification_routes.py`
  - `repository*.py`/`repositories*.py` -> `event_repository*.py`, `connector_repository.py`, `monitoring_repository.py`, `operational_repository_v2.py`
- Normalized v2 route module naming to suffix form (`routes_*_v2.py`).
- Renamed frontend feature directories to `{feature}.content`.
- Renamed frontend live stream hook `useLiveAlerts.ts` -> `useRiskStream.ts` and switched callers.
- Renamed backend tests to dotted `*.test.py` naming (import-safe underscore segments).
- Renamed docs to `{domain}.{topic}.md` including UI phase docs.

## Protocol Compatibility Cutover

- Added standardized primary RabbitMQ naming defaults (`risk.event.*`, `risk.alert.*`, `risk.metric.*`, `risk.reference-data.*`) and retained legacy names.
- Topology now declares/binds both primary and legacy exchanges/queues/routing keys during compatibility window.
- Added `publish_json_with_compat()` to dual-publish primary + legacy routes where required.
- Added standardized primary Redis channels (`risk.live.alerts`, `risk.live.metrics`) and retained legacy channels.
- Notification bridge now dual publishes and dual subscribes for Redis channels.
- Added `/ws/risk-stream` while preserving `/ws/stream` and `/ws/alerts`.
- Frontend stream URL switched to `/ws/risk-stream`.

## Build/Runtime Reference Updates

- Updated `docker-compose.yml` Dockerfile paths to `services/risk/*`.
- Updated all backend Dockerfiles COPY paths to renamed service directories.
- Updated `.github/workflows/ci.yml` backend requirements and Dockerfile matrix paths.
- Updated local setup/start scripts to renamed service directories.

## Test & Script Standardization

- Backend pytest discovery extended for `*.test.py` and configured with `--import-mode=importlib`.
- Frontend scripts standardized to `dev`, `build`, `test`, `lint`.
- Added standardized scripts:
  - `scripts/dev.start.sh`
  - `scripts/dev.reset.sh`
  - `scripts/dev.seed.sh`
  - `scripts/prod.build.sh`

## Dependency Rationalization

- Introduced shared backend base requirements: `backend/services/risk/requirements.base.txt`.
- Service requirements now extend from base and keep service-specific dependencies.
- Removed unused frontend dev dependency: `rollup-plugin-visualizer`.

## Validation Snapshot

- `python3 -m compileall backend` passed.
- `pytest -q` passed (`35 passed`).
- Frontend `npm run lint`, `npm test`, `npm run build` passed.
- Router/WebSocket inventory confirms legacy + new websocket routes are mounted.
- `docker compose config` passed.
- `docker compose build api-gateway` could not run in this environment (Docker daemon unavailable).
