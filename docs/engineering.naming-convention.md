# Engineering Naming Convention

## 1. Global Principles

- Use lowercase for all file and directory names unless language/runtime constraints require otherwise.
- Do not use spaces in paths.
- Use hyphen-separated names for multi-word directories outside language package constraints.
- Favor domain-driven structure over technical dumping grounds.
- Every module name must communicate business intent.
- Disallow ambiguous/generic names such as `utils.py`, `helpers.ts`, `misc.py`, `common.ts` when intent-specific alternatives exist.

## 2. Canonical-to-Filesystem Mapping

Canonical naming remains dotted for architecture and documentation. Filesystem layout remains import-safe per runtime:

- Canonical folder `risk.api` -> filesystem `risk/api/`
- Canonical folder `risk.service` -> filesystem `risk/service/`
- Canonical file `risk.alert.router.py` -> filesystem `risk/alert/router.py`
- Canonical file `risk.autoencoder.model.py` -> filesystem `risk/autoencoder/model.py`

## 3. Backend (Python/FastAPI)

### 3.1 Folder Naming

Canonical pattern:

- `{domain}.{layer}`

Approved layers:

- `api`
- `service`
- `repository`
- `model`
- `worker`
- `enrichment`
- `metrics`
- `notification`
- `ml`

Examples:

- `risk.api`
- `risk.service`
- `risk.repository`
- `risk.model`
- `risk.worker`
- `risk.enrichment`
- `risk.metrics`
- `risk.notification`
- `risk.ml`

### 3.2 File Naming

Canonical pattern:

- `{domain}.{capability}.{type}.py`

Examples:

- `risk.alert.router.py`
- `risk.alert.service.py`
- `risk.alert.repository.py`
- `risk.alert.schema.py`
- `risk.alert.model.py`
- `risk.alert.consumer.py`
- `risk.alert.publisher.py`
- `risk.autoencoder.model.py`
- `risk.autoencoder.trainer.py`

Import-safe filesystem mapping:

- `risk/alert/router.py`
- `risk/alert/service.py`
- `risk/alert/repository.py`
- `risk/autoencoder/model.py`
- `risk/autoencoder/trainer.py`

### 3.3 Variable Naming

- Use `snake_case` only.
- Single-letter variables are only permitted as tight loop counters.
- Do not use abbreviations like `cfg`, `svc`, `mgr`, `ctx` when explicit names are feasible.
- Prefer explicit semantic names.

Examples:

- `risk_event_payload`
- `alert_threshold_score`
- `redis_pubsub_client`

### 3.4 Class Naming

- Use `PascalCase`.
- Name must include one of the required suffixes when applicable:
  - `Service`
  - `Repository`
  - `Router`
  - `Manager`
  - `Client`
  - `Consumer`
  - `Publisher`

Examples:

- `RiskAlertService`
- `RiskEventConsumer`
- `TensorflowAutoencoderModel`

## 4. Frontend (React/TypeScript)

### 4.1 Folder Naming

Pattern:

- `{feature}.content`

Examples:

- `risk-dashboard.content`
- `alert-monitor.content`
- `metrics-stream.content`
- `model-management.content`

### 4.2 Component File Naming

Pattern:

- `{Feature}{ComponentType}.tsx`

Examples:

- `RiskDashboardPage.tsx`
- `AlertStreamPanel.tsx`
- `MetricsLiveChart.tsx`
- `ModelActivationModal.tsx`

### 4.3 Hooks

Pattern:

- `use{Feature}{Purpose}.ts`

Examples:

- `useRiskStream.ts`
- `useAlertFeed.ts`

### 4.4 State Stores

Pattern:

- `{domain}Store.ts`

Examples:

- `riskStore.ts`
- `alertStore.ts`

## 5. Documentation Naming

All documentation must follow:

- `{domain}.{topic}.md`

Examples:

- `risk.architecture.md`
- `risk.event-flow.md`
- `ml.autoencoder.training.md`
- `infra.deployment.md`
- `engineering.naming-convention.md`

Multi-segment topics are permitted:

- `ui-makeover.phase-1.performance-report.md`
- `engineering.phase-03.diff-summary.md`

## 6. Anti-Pattern List

Disallowed unless justified and documented:

- Version suffix in filenames where route/version scope can encode version (`*_v2.py`, `routes_v2_*.py`).
- Generic catch-all modules (`utils.py`, `helpers.ts`, `misc.py`, `common.py`) for business logic.
- Mixed naming conventions in the same folder (`snake_case`, `kebab-case`, `PascalCase`) without purpose.
- Abbreviated variable names that hide intent.

## 7. Enforcement Expectations

- New code and refactors must conform to this specification.
- Runtime-safe adapters are required when canonical naming differs from language import constraints.
- Compatibility windows must be documented for protocol-level names (queues, channels, routes) when changed.
