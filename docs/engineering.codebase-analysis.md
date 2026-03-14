# Aegis AI: Comprehensive Codebase Analysis

## Context

Aegis AI is a distributed real-time AI risk monitoring platform for financial transaction anomaly detection. This analysis covers the original product intention, identified flaws, and what remains missing for full functionality.

---

## 1. Product Vision vs. Reality

### What Aegis AI intends to be

A production-grade, multi-tenant SaaS platform where:
- Financial events are ingested via REST APIs
- Events flow through RabbitMQ to an event worker
- A TensorFlow autoencoder scores events for anomalies
- Results are enriched with external intelligence (OFAC, FATF, ECB, MaxMind, etc.)
- Alerts stream live over WebSocket to analyst dashboards
- Three UIs serve different personas: analyst dashboard, tenant admin console, platform ops console
- Kubernetes-based production deployment with full observability

### Where it actually stands

| Layer | Readiness | Notes |
|-------|-----------|-------|
| Backend services (8 microservices) | **75-85%** | Core event pipeline functional. Security gaps. |
| Frontend UIs (3 apps) | **90-95%** | Nearly feature-complete. All serve dev servers in Docker. |
| ML inference | **60%** | Real TensorFlow autoencoder, but bootstraps on random data. |
| Data connectors | **70%** | OFAC/FATF/ECB enabled. MaxMind/HIBP/OpenSanctions disabled. |
| Kubernetes infra | **15%** | Deployments exist. No Services, Ingress, probes, NetworkPolicy. |
| CI/CD | **40%** | Builds and tests run. No image push, no deploy, no scanning. |
| SDK ecosystem | **5%** | JS/Python/.NET skeletons only. |
| Production upgrade roadmap | **~30%** | PR1-PR2 done of 7-PR plan. |

**Bottom line**: Well-architected MVP that works in Docker Compose. Not deployable to any real environment. Has security flaws unacceptable even in staging.

---

## 2. Critical Flaws (Must Fix Before Any Production Use)

### CRIT-01: Default JWT secrets with no startup enforcement
- **Where**: `backend/libs/common/risk_common/config.py` lines 71-74, 89-91
- **What**: JWT keys default to `"change-me-in-prod"`. Validation only triggers when `ENVIRONMENT=production`. Any other env runs with known secrets.
- **Impact**: Attacker who reads this repo can forge valid JWTs for any tenant.
- **Fix**: Startup warning for all envs; hard refusal for staging; random ephemeral secret when placeholder detected in non-dev.

### CRIT-02: Hardcoded admin seed with known password
- **Where**: `infra/postgres/init/001_schema.sql` lines 50-52
- **What**: Seeds `admin` / `admin123` with full privileges.
- **Impact**: Anyone with network access + knowledge of this default can authenticate as admin.
- **Fix**: Remove hardcoded seed. Add first-run CLI that generates random password.

### CRIT-03: SMTP email delivery has no authentication or TLS
- **Where**: `backend/services/risk/alert_router/app/application/router.py` lines 60-78
- **What**: Raw `smtplib.SMTP` connection, no STARTTLS, no auth, no cert verification.
- **Impact**: Alert emails interceptable in transit. Most production SMTP relays will reject.
- **Fix**: Add SMTP username/password/TLS config options. Use `SMTP_SSL` or `starttls()`.

### CRIT-04: Webhook delivery has no HMAC signature verification
- **Where**: `alert_router/app/application/router.py` lines 85-93; signing secret defined in `config.py` line 173 but **never used**
- **What**: `alert_router_webhook_signing_secret` config key exists but webhook POST never includes a signature header.
- **Impact**: Webhook consumers cannot verify payload authenticity. Fake alert injection possible.
- **Fix**: Compute `HMAC-SHA256(signing_secret, body)`, send as `X-Aegis-Signature` header.

### CRIT-05: Kubernetes manifests are undeployable
- **Where**: `infra/eks/base/deployments.yaml`, `infra/eks/base/kustomization.yaml`
- **What**: 7 Deployments defined but **zero** Service, Ingress, NetworkPolicy, or HPA resources. No liveness/readiness probes. No resource limits. No securityContext (containers run as root).
- **Impact**: Pods cannot communicate. External traffic cannot reach cluster. No health detection. Single pod can OOM-kill entire node.
- **Fix**: Full Kubernetes manifest rewrite (see Phase 2 below).

### CRIT-06: Frontend Dockerfiles serve development servers in production
- **Where**: All three `frontend/*/Dockerfile` — `CMD ["npm", "run", "dev"]`
- **What**: Vite dev server with HMR, source maps, unoptimized bundles.
- **Impact**: Exposes source maps, no caching headers, unminified JS, not designed for production traffic.
- **Fix**: Multi-stage Dockerfiles: build stage `npm run build`, prod stage serves `dist/` via nginx.

### CRIT-07: Hardcoded fallback to `tenant-alpha` on auth failure
- **Where**:
  - `backend/services/risk/api/app/infrastructure/monitoring_repository.py` line 152
  - `frontend/control-tenant/src/App.tsx` lines 57, 68, 91, 120, 124
  - `frontend/dashboard/src/widgets/layout/AppShell.tsx` line 43
  - `backend/services/risk/connector/app/application/scheduler.py` line 432
- **What**: Missing `tenant_id` in JWT silently resolves to `tenant-alpha` instead of denying access.
- **Impact**: Tenant isolation bypass. Corrupted/forged token accesses real tenant data.
- **Fix**: Return 401/403 when tenant cannot be resolved. Make config key mandatory.

---

## 3. Missing Functionality (Prevents Full Product Operation)

### MISS-01: No rate limiting on any API endpoint
- **Where**: `backend/services/risk/api/app/main.py` — no middleware
- **Impact**: Single client can saturate event pipeline, exhaust DB connections, flood ML service.
- **Fix**: Add `slowapi` or custom Redis-backed rate limiter. Per-tenant and per-endpoint limits.

### MISS-02: No CSRF protection on control plane
- **Where**: `backend/services/risk/control_plane/app/api/deps.py` lines 17-44
- **What**: Cookie-based JWT auth with no CSRF token verification.
- **Impact**: Malicious site can trigger tenant config changes, model activation, alert destination creation.
- **Fix**: Double-submit cookie CSRF or require `Authorization: Bearer` header for mutations.

### MISS-03: CI/CD has no deployment stage
- **Where**: `.github/workflows/ci.yml` lines 115-143
- **What**: Docker images built but never pushed. No deployment job. Control-tenant/ops tests not run (only lint).
- **Fix**: Add image push to GHCR/ECR, deployment stage, `npm test` for all frontends.

### MISS-04: No container scanning or SAST
- **Where**: `.github/workflows/ci.yml`, `.pre-commit-config.yaml`
- **What**: Only gitleaks for secrets. No Trivy/Snyk, no Bandit, no ESLint security.
- **Fix**: Add Trivy after image build, `bandit -r backend/`, `npm audit`.

### MISS-05: No production environment configuration
- **Where**: Only `.env.example` exists. No `.env.production` or staging template.
- **Fix**: Create `.env.production.template` with mandatory markers.

### MISS-06: PEP enrichment source attribution is a `pass` stub
- **Where**: `backend/services/risk/worker/app/application/enrichment.py` lines 131-133
- **What**: PEP match sets `signals["pep_hit"] = True` but source attribution line is `pass`.
- **Impact**: Compliance audit trails cannot trace PEP decisions to data sources.
- **Fix**: Replace `pass` with `sources.append(...)` using actual source from DB row.

### MISS-07: IP/BIN enrichment cache miss falls through silently
- **Where**: `backend/services/risk/enrichment/app/application/feature_enrichment_service.py` lines 73, 103
- **What**: Cache miss → `pass`. No logging, no fallback, no provenance entry.
- **Impact**: High-risk transactions score low because enrichment data was simply missing.
- **Fix**: Log cache misses, add provenance with `cache_hit: False`, queue background refresh.

### MISS-08: Three WebSocket endpoints serve identical functionality
- **Where**: `backend/services/risk/notification/app/api/notification_routes.py` lines 72-84
- **What**: `/ws/alerts`, `/ws/stream`, `/ws/risk-stream` all call same `_run_stream`.
- **Fix**: Designate one as canonical, deprecate others with logged warnings and sunset date.

---

## 4. Technical Debt

### Architecture
- **TD-A1**: Legacy/primary dual-publish pattern doubles all RabbitMQ message traffic (`risk_common/messaging.py`, every publisher)
- **TD-A2**: V1 and V2 API coexistence with no deprecation timeline (`docs/risk.v2-operationalization.md`)
- **TD-A3**: `assert runtime is not None` for control flow — disabled by Python `-O` flag (`connector/app/application/scheduler.py` line 120)

### Code Quality
- **TD-C1**: Vite version mismatch: dashboard `^5.3.4`, control apps `^7.3.1`
- **TD-C2**: No OpenAPI schema generation — frontend types manually duplicated from backend Pydantic models
- **TD-C3**: Broad `except Exception` in ~15 places, some swallow DB connection failures
- **TD-C4**: All SQL via `text()` string literals instead of ORM/query builders

### Testing (~40% coverage of critical paths)
- **TD-T1**: Missing tests: end-to-end event pipeline, alert delivery, connector scheduling, multi-tenant isolation, DLQ exhaustion, enrichment cache miss
- **TD-T2**: Control-tenant/ops tests not run in CI (only lint)
- **TD-T3**: Zero integration tests (no cross-service verification)

### Infrastructure
- **TD-I1**: Caddyfile has no WebSocket timeout, compression, or health-check proxying
- **TD-I2**: Kustomize overlays only patch ServiceAccounts, not images/replicas/resources
- **TD-I3**: Docker Compose RabbitMQ uses `guest:guest` on exposed port 15672
- **TD-I4**: No Prometheus/Sentry integration despite stubs in config

### Documentation Contradictions
- Validation report (2026-03-02) shows "all 9 checks passed" but release baseline (2026-03-07) lists 4 confirmed blockers — scopes differ but naming creates confusion
- Alert Router is fully implemented but absent from architecture diagram and README service list
- Production upgrade plan PR3-PR7 marked unstarted but features from PR4 (refresh tokens, RBAC) exist in code

---

## 5. Recommended Action Plan

### Phase 0: Security Triage (blocks everything)
| Task | Key Files |
|------|-----------|
| Remove hardcoded admin seed; add random-password CLI init | `infra/postgres/init/001_schema.sql` |
| Startup warning/refusal for default JWT secrets in all envs | `risk_common/config.py` |
| Remove all `tenant-alpha` fallbacks; deny on missing tenant | 6 files across backend + frontend |
| Add HMAC signatures to webhook delivery | `alert_router/app/application/router.py` |
| Add TLS+auth to SMTP email delivery | `alert_router/app/application/router.py`, `config.py` |
| Add CSRF protection to control plane | `control_plane/app/api/deps.py` |
| Replace `assert` with explicit check | `connector/app/application/scheduler.py` |
| Add rate limiting middleware | `api/app/main.py` |

### Phase 1: Frontend Production Readiness
| Task | Key Files |
|------|-----------|
| Rewrite Dockerfiles as multi-stage builds (build + nginx) | 3 Dockerfiles |
| Unify Vite version across frontends | 3 `package.json` |
| Add `npm test` for control-tenant/ops to CI | `ci.yml` |
| Create `.env.production.template` | New file |

### Phase 2: Kubernetes Manifests
| Task | Key Files |
|------|-----------|
| Create Service resources for all deployments | New `services.yaml` |
| Add liveness/readiness probes | `deployments.yaml` |
| Add resource requests/limits | `deployments.yaml` |
| Add securityContext (non-root, read-only FS) | `deployments.yaml` |
| Create Ingress resources | New `ingress.yaml` |
| Add NetworkPolicy for pod isolation | New `networkpolicies.yaml` |
| Add HPA for key services | New `hpa.yaml` |
| Add PVC for ML model storage | New `pvc.yaml` |

### Phase 3: CI/CD Completion
| Task | Key Files |
|------|-----------|
| Add Docker image push to registry | `ci.yml` |
| Add Trivy container scanning | `ci.yml` |
| Add Bandit SAST | `ci.yml` |
| Add deployment stage | `ci.yml` or new workflow |
| Add integration test job | New workflow |

### Phase 4: Enrichment & Data Quality
| Task | Key Files |
|------|-----------|
| Fix PEP source attribution stub | `enrichment.py` line 133 |
| Add cache miss logging and provenance | `feature_enrichment_service.py` |
| Deprecate duplicate WebSocket endpoints | `notification_routes.py` |
| Remove or document legacy dual-publish sunset | `messaging.py` + all callers |

### Phase 5: Testing & Observability
| Task | Key Files |
|------|-----------|
| End-to-end event pipeline tests | New test files |
| Alert router delivery tests | New test file |
| Multi-tenant isolation tests | New test file |
| Prometheus metrics endpoints | Each service `main.py` |
| Sentry integration | Each service `main.py` |
