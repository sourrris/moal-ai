# V2 Operationalization Guide

This repository now includes the foundational v2 operational stack for transaction fraud monitoring.

## What was added

- Alembic migration framework (`backend/alembic.ini`, `backend/alembic/`)
- Baseline v2 migration (`20260228_0001`) with:
  - partitioned `events_v2` (daily range + hash subpartitions by `tenant_id`)
  - connector/reference/model/audit/metrics tables
  - row-level security policies for tenant-scoped tables
- Tenant-aware JWT + refresh token flow (`/v2/auth/token`, `/v2/auth/refresh`)
- V2 API surface in API Gateway:
  - `/v2/events/ingest`, `/v2/events/ingest/batch`
  - `/v2/alerts` lifecycle endpoints
  - `/v2/risk-decisions/{event_id}`
  - `/v2/data-sources/*`
  - `/v2/models/*`
- Event worker v2 processing path:
  - enrichment + rules + risk decision composition
  - writes `event_enrichments`, `risk_decisions`, `alerts_v2`
- Notification websocket multiplexing:
  - `/ws/stream?channels=alerts,metrics`
- New services:
  - `data_connector`
  - `feature_enrichment`
  - `metrics_aggregator`
- Connector runtime state:
  - `source_connector_state` tracks per-source cursor/backoff/degraded status
  - `/v1/connectors/*` includes status/runs/errors/enable/disable/run-now + on-demand lookup routes
- Auth refresh-session table:
  - `refresh_sessions` supports cookie-based refresh token rotation/logout revocation

## Applying migrations

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://risk:risk@localhost:5432/risk_monitor alembic -c alembic.ini upgrade head
```

## Local startup (non-Docker)

`./scripts/local/setup.sh` now installs new service dependencies and runs Alembic.

`./scripts/local/start.sh` now starts:
- data connector (`:8030`)
- feature enrichment (`:8040`)
- metrics aggregator (`:8050`)

## Docker startup

`docker-compose.yml` now includes the same three services.

## Notes

- `/v1/*` routes and behavior remain available for compatibility.
- `/v2/events/ingest` performs dual-write bootstrap to v1 (`events`) and v2 (`events_v2`).
- Tenant enforcement for v2 relies on JWT `tenant_id` claim and DB RLS context (`app.current_tenant`).
- Notification websocket fanout is tenant-scoped in `/ws/stream` and `/ws/alerts`.
