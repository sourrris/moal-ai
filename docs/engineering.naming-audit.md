# Engineering Naming Audit

Audit scope covered all tracked files under backend, frontend, scripts, infra, CI, and docs before refactor execution.

## Detection Categories

- Generic file naming (`service.py`, `services.py`, `routes.py`, `repository.py`, `repositories.py`)
- Mixed version naming (`routes_v2_*`, `*_v2`)
- Inconsistent folder naming (underscore service directories)
- Frontend feature-folder style drift
- Documentation naming inconsistency
- Test naming inconsistency
- Protocol-sensitive contract names (RabbitMQ/Redis/WebSocket)

## Path Audit

| Current Path | Proposed New Path | Reason for Change | Risk Level |
|---|---|---|---|
| `backend/services/api_gateway` | `backend/services/risk/api` | Domain-driven service naming | high |
| `backend/services/event_worker` | `backend/services/risk/worker` | Domain-driven service naming | high |
| `backend/services/ml_inference` | `backend/services/risk/ml` | Domain-driven service naming | high |
| `backend/services/notification_service` | `backend/services/risk/notification` | Domain-driven service naming | high |
| `backend/services/data_connector` | `backend/services/risk/connector` | Domain-driven service naming | high |
| `backend/services/feature_enrichment` | `backend/services/risk/enrichment` | Domain-driven service naming | high |
| `backend/services/metrics_aggregator` | `backend/services/risk/metrics` | Domain-driven service naming | high |
| `backend/services/api_gateway/app/application/services.py` | `backend/services/risk/api/app/application/risk_event_service.py` | Remove generic module name | medium |
| `backend/services/feature_enrichment/app/application/service.py` | `backend/services/risk/enrichment/app/application/feature_enrichment_service.py` | Remove generic module name | medium |
| `backend/services/ml_inference/app/application/service.py` | `backend/services/risk/ml/app/application/model_inference_service.py` | Remove generic module name | medium |
| `backend/services/data_connector/app/api/routes.py` | `backend/services/risk/connector/app/api/connector_routes.py` | Remove generic route module name | medium |
| `backend/services/feature_enrichment/app/api/routes.py` | `backend/services/risk/enrichment/app/api/enrichment_routes.py` | Remove generic route module name | medium |
| `backend/services/ml_inference/app/api/routes.py` | `backend/services/risk/ml/app/api/model_routes.py` | Remove generic route module name | medium |
| `backend/services/notification_service/app/api/routes.py` | `backend/services/risk/notification/app/api/notification_routes.py` | Remove generic route module name | high |
| `backend/services/data_connector/app/infrastructure/repository.py` | `backend/services/risk/connector/app/infrastructure/connector_repository.py` | Remove generic repository name | medium |
| `backend/services/event_worker/app/infrastructure/repository.py` | `backend/services/risk/worker/app/infrastructure/event_repository.py` | Remove generic repository name | medium |
| `backend/services/event_worker/app/infrastructure/repository_v2.py` | `backend/services/risk/worker/app/infrastructure/event_repository_v2.py` | Normalize v2 module naming | medium |
| `backend/services/api_gateway/app/infrastructure/repositories.py` | `backend/services/risk/api/app/infrastructure/monitoring_repository.py` | Remove generic plural repository name | medium |
| `backend/services/api_gateway/app/infrastructure/repositories_v2.py` | `backend/services/risk/api/app/infrastructure/operational_repository_v2.py` | Remove generic plural repository name | medium |
| `backend/services/api_gateway/app/api/routes_v2_alerts.py` | `backend/services/risk/api/app/api/routes_alerts_v2.py` | Version token normalization | medium |
| `backend/services/api_gateway/app/api/routes_v2_data_sources.py` | `backend/services/risk/api/app/api/routes_data_sources_v2.py` | Version token normalization | medium |
| `backend/services/api_gateway/app/api/routes_v2_events.py` | `backend/services/risk/api/app/api/routes_events_v2.py` | Version token normalization | medium |
| `backend/services/api_gateway/app/api/routes_v2_models.py` | `backend/services/risk/api/app/api/routes_models_v2.py` | Version token normalization | medium |
| `backend/services/api_gateway/app/api/routes_v2_risk_decisions.py` | `backend/services/risk/api/app/api/routes_risk_decisions_v2.py` | Version token normalization | medium |
| `frontend/dashboard/src/features/overview` | `frontend/dashboard/src/features/risk-dashboard.content` | Enforce `{feature}.content` | medium |
| `frontend/dashboard/src/features/alerts` | `frontend/dashboard/src/features/alert-monitor.content` | Enforce `{feature}.content` | medium |
| `frontend/dashboard/src/features/events` | `frontend/dashboard/src/features/event-stream.content` | Enforce `{feature}.content` | medium |
| `frontend/dashboard/src/features/models` | `frontend/dashboard/src/features/model-management.content` | Enforce `{feature}.content` | medium |
| `frontend/dashboard/src/features/settings` | `frontend/dashboard/src/features/platform-settings.content` | Enforce `{feature}.content` | medium |
| `frontend/dashboard/src/features/auth` | `frontend/dashboard/src/features/access-auth.content` | Enforce `{feature}.content` | medium |
| `frontend/dashboard/src/shared/hooks/useLiveAlerts.ts` | `frontend/dashboard/src/shared/hooks/useRiskStream.ts` | Hook naming standardization | medium |
| `backend/tests/test_api_gateway_smoke.py` | `backend/tests/risk.api_gateway.smoke.test.py` | Dotted backend test naming | low |
| `backend/tests/test_auth_rs256_sessions.py` | `backend/tests/risk.auth.rs256_sessions.test.py` | Dotted backend test naming | low |
| `backend/tests/test_jwt_claims_v2.py` | `backend/tests/risk.auth.jwt_claims_v2.test.py` | Dotted backend test naming | low |
| `backend/tests/test_metrics_drift_logic.py` | `backend/tests/risk.metrics.drift_logic.test.py` | Dotted backend test naming | low |
| `backend/tests/test_models_routes_contract.py` | `backend/tests/risk.models.routes_contract.test.py` | Dotted backend test naming | low |
| `backend/tests/test_models_serialization.py` | `backend/tests/risk.models.serialization.test.py` | Dotted backend test naming | low |
| `backend/tests/test_models_training_flow.py` | `backend/tests/risk.models.training_flow.test.py` | Dotted backend test naming | low |
| `backend/tests/test_notification_tenant_routing.py` | `backend/tests/risk.notification.tenant_routing.test.py` | Dotted backend test naming | low |
| `backend/tests/test_password_hashing.py` | `backend/tests/risk.auth.password_hashing.test.py` | Dotted backend test naming | low |
| `backend/tests/test_settings_env_aliases.py` | `backend/tests/risk.settings.env_aliases.test.py` | Dotted backend test naming | low |
| `backend/tests/test_settings_production_validation.py` | `backend/tests/risk.settings.production_validation.test.py` | Dotted backend test naming | low |
| `backend/tests/test_v2_schemas.py` | `backend/tests/risk.schemas.v2_contract.test.py` | Dotted backend test naming | low |
| `backend/tests/test_worker_repository_jsonb.py` | `backend/tests/risk.worker.repository_jsonb.test.py` | Dotted backend test naming | low |
| `docs/architecture.md` | `docs/risk.architecture.md` | Documentation naming standardization | low |
| `docs/folder-structure.md` | `docs/engineering.folder-structure.md` | Documentation naming standardization | low |
| `docs/production-upgrade-plan.md` | `docs/engineering.production-upgrade-plan.md` | Documentation naming standardization | low |
| `docs/project-access-guide.md` | `docs/engineering.project-access-guide.md` | Documentation naming standardization | low |
| `docs/v2-operationalization.md` | `docs/risk.v2-operationalization.md` | Documentation naming standardization | low |
| `docs/audit/pr1-audit-ci-baseline.md` | `docs/engineering.audit.pr1-ci-baseline.md` | Documentation naming standardization | low |
| `docs/ui-makeover/phase-*/a11y-audit.md` | `docs/ui-makeover/phase-*/ui-makeover.phase-*.a11y-audit.md` | Documentation naming standardization | low |
| `docs/ui-makeover/phase-*/bundle-analysis.md` | `docs/ui-makeover/phase-*/ui-makeover.phase-*.bundle-analysis.md` | Documentation naming standardization | low |
| `docs/ui-makeover/phase-*/code-summary.md` | `docs/ui-makeover/phase-*/ui-makeover.phase-*.code-summary.md` | Documentation naming standardization | low |
| `docs/ui-makeover/phase-*/deploy-notes.md` | `docs/ui-makeover/phase-*/ui-makeover.phase-*.deploy-notes.md` | Documentation naming standardization | low |
| `docs/ui-makeover/phase-*/mobile-checklist.md` | `docs/ui-makeover/phase-*/ui-makeover.phase-*.mobile-checklist.md` | Documentation naming standardization | low |
| `docs/ui-makeover/phase-*/mockups.md` | `docs/ui-makeover/phase-*/ui-makeover.phase-*.mockups.md` | Documentation naming standardization | low |
| `docs/ui-makeover/phase-*/performance-report.md` | `docs/ui-makeover/phase-*/ui-makeover.phase-*.performance-report.md` | Documentation naming standardization | low |

## Duplicate Logic and Orphaned Files Assessment

- Potential duplicate-logic naming clusters were identified around generic backend modules (`service.py`, `repository.py`, `routes.py`) and are mapped above to intent-specific module names.
- No orphaned tracked source files were detected in this pass; the only tracked non-source artifact identified for cleanup was `frontend/dashboard/tsconfig.tsbuildinfo`.

## Protocol-Sensitive Items (Explicit High-Risk)

| Current Contract | Proposed Contract | Reason for Change | Risk Level |
|---|---|---|---|
| `/ws/stream` | `/ws/risk-stream` (legacy routes retained) | WebSocket stream naming standardization | high |
| `risk.alerts.live` | `risk.live.alerts` (dual channel publish/subscribe) | Redis channel normalization | high |
| `risk.metrics.live` | `risk.live.metrics` (dual channel publish/subscribe) | Redis channel normalization | high |
| `risk.events.ingested` | `risk.event.ingested` (legacy routing retained) | Rabbit routing standardization | high |
| `risk.events.v2.ingested` | `risk.event.v2.ingested` (legacy routing retained) | Rabbit routing standardization | high |
| `risk.alerts.raised` | `risk.alert.raised` (legacy routing retained) | Rabbit routing standardization | high |
| `risk.metrics.updated` | `risk.metric.updated` (legacy routing retained) | Rabbit routing standardization | high |
| `risk.reference.updated` | `risk.reference-data.updated` (legacy routing retained) | Rabbit routing standardization | high |
