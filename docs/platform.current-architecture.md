# Aegis AI Current Architecture Assessment (Phase 0)

## Scope and Date
- Assessment date: March 2, 2026
- Codebase scope: `/backend/services/risk/*`, `/backend/libs/common/risk_common/*`, `/frontend/dashboard/*`
- This document captures current-state architecture before modular connector-driven migration.

## Event Ingestion Flow

### Legacy v1 ingestion path
1. `POST /v1/events/ingest` (`backend/services/risk/api/app/api/routes_events.py`) accepts `EventIngestRequest`.
2. API gateway stores event in legacy `events` table via `EventRepository.create_if_absent`.
3. API gateway publishes legacy `EventEnvelope` to RabbitMQ `risk.event.exchange` + legacy exchange using `publish_json_with_compat`.
4. Worker consumes from `risk.event.queue` (`handle_message` in `worker/app/application/processor.py`).

### v2 ingestion path
1. `POST /v2/events/ingest` and `/v2/events/ingest/batch` (`routes_events_v2.py`) accept `RiskEventIngestRequest`.
2. API gateway writes to `events_v2` and idempotency table (`event_idempotency_keys`) via `EventV2Repository.create_if_absent`.
3. API gateway performs compatibility dual-write:
- Persists derived legacy `EventEnvelope` to `events`.
- Publishes both v1 and v2 event messages.
4. Worker consumes v2 messages from `risk.event.v2.queue` (`handle_message_v2`).

### Connector-triggered ingestion
- Connector scheduler can auto-ingest synthetic reference-update events by calling API `POST /v2/events/ingest` and `/v2/events/ingest/batch`.

## ML Inference Flow

### Runtime scoring
1. Worker receives event payload.
2. For v1: uses incoming feature vector directly.
3. For v2:
- Resolves enrichment via `feature-enrichment` service (`/v1/enrichment/resolve`) with DB fallback.
- Builds feature vector in worker (`_build_feature_vector`).
- Calls ML service `POST /v1/infer` with `InferenceRequest(event_id, tenant_id, features)`.
4. Worker persists decision data:
- v1: `anomaly_results`, `events.status`.
- v2: `event_enrichments`, `risk_decisions`, `alerts_v2`, `events_v2.status`.

### Model lifecycle
- ML service (`backend/services/risk/ml`) manages TensorFlow autoencoder training and activation.
- API gateway proxies model operations via `/v1/models/*` and operational analytics via `/v2/models/*`.
- Training for API workflows can use historical `risk_decisions.feature_vector` (compatibility path).

## Alert Emission Flow
1. Worker raises alerts when anomaly/risk thresholds are exceeded.
2. Alerts are published to RabbitMQ alert exchange (`risk.alert.exchange` + legacy exchange).
3. Notification service consumes alert and metrics queues.
4. Notification bridge republishes payloads to Redis channels (`risk.live.alerts`, `risk.live.metrics`, plus legacy channels).
5. WebSocket layer fans out tenant-scoped alerts/metrics to clients (`/ws/alerts`, `/ws/stream`, `/ws/risk-stream`).

## Vendor-Specific Couplings

### Connector service
- Vendor logic is embedded directly in service code (`connector/app/application/connectors.py`):
- OFAC SLS parsing
- FATF HTML parsing
- ECB FX parsing
- mempool.space bitcoin mapping
- abuse.ch IP blocklist mapping
- Runtime scheduler directly instantiates vendor connector classes via `default_connectors()`.

### Worker and enrichment dependencies on source-specific fields
- Risk logic depends on transaction attributes tied to source capabilities:
- `source_ip`, `card_bin`, `merchant_id`, country fields, metadata shape.
- Rules and feature extraction implicitly assume payment/fraud schema semantics.

## Areas Where Logic Is Tightly Bound to Source Format
- `RiskEventIngestRequest.transaction` is passed through to DB payload and reused by worker/rules with limited abstraction.
- `_legacy_features()` and `_build_feature_vector()` are hand-crafted around current transaction shape and enrichment keys.
- Connector outputs map directly into existing DB cache tables with source-specific assumptions.
- Enrichment queries match exact cache table columns and source names (for example `ofac_sls`, `ecb_fx`).

## Multi-Tenancy Readiness

### Existing strengths
- Tenant-aware JWT claims and scope enforcement on v2 endpoints.
- `tenants` table and role bindings (`user_tenant_roles`).
- Row-level security policies for key v2 tables.
- `set_tenant_context` used in repositories to align DB session tenant context.
- Tenant-scoped WebSocket routing.

### Current gaps
- No centralized tenant configuration table for thresholds/rule overrides/model pinning.
- Legacy v1 flows are partially tenant-aware but not uniformly RLS-enforced.
- Connector runtime/state is mostly source-global; not tenant-targeted configuration.
- Some processing thresholds and rules are hardcoded in worker.

## Areas Not Suitable for SDK Exposure
- Internal queue/exchange names, routing keys, and compatibility dual-publish details.
- Internal connector scheduler control and raw run/error operational tables.
- Legacy compatibility payload internals (`EventEnvelope`, synthetic connector auto-ingest metadata).
- Internal enrichment source cache schema and source-specific provenance keys.
- Worker retry/dead-letter control headers (`x-retry-count`, internal DLX semantics).

## Constraints Observed in Current Architecture
- Event bus compatibility is actively preserved through dual exchange/routing-key publication.
- Legacy and v2 paths coexist and share some persistence/processing code.
- ML logic combines model score and deterministic rules in v2 risk decisions.
