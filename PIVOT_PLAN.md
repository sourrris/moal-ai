# moal-ai Pivot Plan

**Status:** Planning phase complete. Ready for execution on `pivot/moal-ai` branch.  
**Date:** 2026-04-06  
**Project:** Aegis AI → moal-ai  

---

## Context Summary

### What This Is
A complete refactoring plan to transform "aegisai" (an overengineered 9-microservice risk monitoring portfolio project) into **moal-ai** — a focused, self-hosted user behavior anomaly detection tool for security engineers.

### Why We're Doing This
The original project was built primarily to showcase ML, distributed systems, auth, and system design skills to recruiters. It works but is massively over-engineered:
- 9 backend microservices (only 1-2 needed)
- 3 frontend apps (should be 1)
- ~30+ database tables (need ~5)
- Full Kubernetes setup (use Docker Compose)
- Transaction-fraud ML (pivot to user behavior anomalies)

### Target User
**Security Engineer / DevSecOps at a startup**
- Self-hosted tool (data stays on-premise)
- Detects user behavior anomalies (UEBA pattern)
- Real product gap in the market (Exabeam, Securonix are enterprise-priced)
- Lightweight enough for small security teams

### Data Model
**User behavior events** (not transactions):
- Auth logs (logins, failures, new devices)
- API calls (request patterns, rates)
- Session activity (duration, source IPs, user agents)

Real features for the autoencoder to learn from (not hash-based noise):
- Hour/day of week (cyclical encoding)
- Failed auth ratio, session duration, request rate
- Device fingerprint novelty, geo distance
- Source IP frequency

### New Product Positioning
moal-ai: **Self-hosted user behavior anomaly detection for security teams**

---

## Current State (Overengineering Audit Results)

### Backend: 9 Services → 1 Service
| Service | Status | Reason |
|---------|--------|--------|
| API Gateway | KEEP | Core auth + event ingestion |
| Event Worker | DELETE | Processing moves inline to API |
| ML Service | KEEP | TensorFlow autoencoder (can stay separate or inline) |
| Connector | DELETE | No external data sources needed |
| Enrichment | DELETE | Depends on connectors |
| Metrics | DELETE | Not MVP priority |
| Notification | DELETE | No WebSocket needed initially |
| Control Plane | DELETE | No multi-tenancy |
| Alert Router | DELETE | No email/Slack/webhook routing |

### Frontend: 3 Apps → 1 App
| App | Status |
|-----|--------|
| dashboard | KEEP |
| control-tenant | DELETE |
| control-ops | DELETE |

### Database: ~30+ Tables → ~5 Tables
| Table | Status |
|-------|--------|
| users | KEEP |
| behavior_events | NEW |
| anomaly_results | KEEP |
| alerts | NEW |
| model_registry | KEEP |
| **Deleted:** events, events_v2, v2 duplicates, connector tables, metrics tables, control plane tables | DELETE | All unnecessary |

### Infrastructure: K8s + 13 Dockerfiles → Docker Compose + 2 Dockerfiles
- Delete `infra/eks/` (Kubernetes)
- Delete `infra/reverse-proxy/` (Caddy, nginx)
- Simplify to 4 Docker services: postgres, db-migrate, api, dashboard
- Delete complex scripts (maintain-partitions, replay-dlq, etc.)

---

## Target Minimal Architecture

```
Client
  ↓
FastAPI (single service)
  ├─ POST /api/events/ingest → Feature engineering → ML inference → Save to DB
  ├─ GET /api/events → List behavior events
  ├─ GET /api/alerts → List flagged events
  ├─ POST /auth/token → Simple JWT auth
  └─ GET /api/models/active → Model metadata

  ↓
PostgreSQL (5 tables)
  - users
  - behavior_events
  - anomaly_results
  - alerts
  - model_registry

  ↓
TensorFlow Autoencoder (separate or inline)
  - Train on real behavioral features
  - Score anomalies synchronously

  ↓
React Dashboard (single Vite app)
  - Overview, Alerts, Events, Models, Login
  - Polling for data (no WebSocket initially)
```

---

## Implementation Plan: 6 Phases

### Phase 1: Rebrand (aegisai → moal-ai)
**Mechanical rename, low risk.**
- Rename `risk_common/` → `moal_common/` (directory + all imports)
- Update all branding strings in code, configs, Docker labels
- Update README.md and CLAUDE.md
- Commit: `chore: rebrand aegisai to moal-ai`

**Files affected:**
- `backend/libs/common/pyproject.toml`
- All Python imports across 9 services
- `frontend/dashboard/package.json`, config files
- `docker-compose.yml` labels
- `README.md`, `CLAUDE.md`

### Phase 2: Strip Overengineered Components
**Delete dead services and code. Worker will be temporarily broken.**
- Delete 6 backend services: connector, enrichment, metrics, notification, control_plane, alert_router
- Delete 2 frontend apps: control-tenant, control-ops
- Delete dead code directories: `backend/risk/`, `backend/risk.connector/`, `aegis-connectors/`
- Delete infrastructure: `infra/eks/`, `infra/reverse-proxy/`, `infra/postgres/init/`
- Delete unnecessary scripts (replay-dlq, maintain-partitions, etc.)
- Remove v1 API routes, v1 auth, OAuth, refresh tokens, RS256, cookie auth
- Remove multi-tenant auth logic
- Simplify `config.py` (~100 params → ~15), delete RabbitMQ/Redis settings
- Clean up backend and E2E tests (delete tests for deleted components)
- Commit: `chore: strip overengineered services and infrastructure`

**Gotchas:**
- Worker becomes non-functional after this phase (fixed in Phase 4)
- `schemas_v2.py` heavily imported by worker — OK to break, will rewrite

### Phase 3: Reshape Data Model
**New schema for behavior events, not transactions.**
- Create Alembic migration dropping ~25 unnecessary tables
- New tables: `behavior_events`, `alerts`
- Keep: `users`, `anomaly_results`, `model_registry`, `model_training_runs`
- Update SQLAlchemy ORM models for new schema
- Rewrite Pydantic schemas (remove transaction-oriented schemas)
- Rewrite repositories to query `behavior_events` instead of old tables
- Delete `tenant_setup_repository.py`, `operational_repository_v2.py`
- Commit: `feat: reshape database schema for behavior events`

**New `behavior_events` columns:**
- user_identifier, event_type (auth/api_call/session), source, source_ip, user_agent
- geo_country, geo_city, hour_of_day, day_of_week
- session_duration_seconds, request_count, failed_auth_count, bytes_transferred
- endpoint, status_code, device_fingerprint, metadata, features[], occurred_at, ingested_at

**New `alerts` columns:**
- event_id, severity, anomaly_score, threshold, model_name, model_version
- state (open/acknowledged/resolved/false_positive), user_identifier, created_at

### Phase 4: Fix ML Pipeline
**Real features, synchronous processing, delete worker.**
- Create `feature_engineering.py`: compute real behavioral features (hour_sin/cos, day_sin/cos, failed_auth_ratio, etc.)
- Inline ML scoring in API (synchronous HTTP call to ML service, or bring TensorFlow directly)
- Rewrite event ingestion endpoint: `POST /api/events/ingest` → persist → score → create alerts
- Delete worker service entirely
- Optional: Create LANL dataset loader for training on real data
- Commit: `feat: real behavioral feature engineering and inline ML scoring`

**Real features to compute:**
1. `hour_of_day_sin/cos` — cyclical encoding of hour
2. `day_of_week_sin/cos` — cyclical encoding of day
3. `source_ip_frequency` — normalized count from this IP in recent window
4. `failed_auth_ratio` — failed_auth_count / request_count
5. `session_duration_norm` — normalized session duration
6. `request_rate` — requests per second, normalized
7. `is_new_device` — 1.0 if device_fingerprint unseen before for this user
8. `bytes_per_request` — bytes_transferred / request_count, normalized
9. `status_error_rate` — 1.0 if status >= 400, else 0.0

### Phase 5: Simplify Infrastructure
**Docker Compose with 4 services, simplified scripts.**
- Rewrite `docker-compose.yml`: postgres, db-migrate, api, dashboard (remove 12 services)
- Create single backend Dockerfile (remove 9 others)
- Simplify `scripts/local/start.sh`, `setup.sh`, `stop.sh`
- Update `.github/workflows/ci.yml` (remove K8s validation, control-ops tests, extra Docker builds)
- Commit: `chore: simplify infrastructure to docker-compose`

**docker-compose.yml services:**
```yaml
postgres:
  image: postgres:16
  environment: DB_URL

db-migrate:
  build: ./backend
  command: alembic upgrade head
  depends_on: [postgres]

api:
  build: ./backend/services/risk/api
  ports: [8000]
  depends_on: [postgres, ml]

ml:
  build: ./backend/services/risk/ml
  ports: [8001]

dashboard:
  build: ./frontend/dashboard
  ports: [5173]
  depends_on: [api]
```

### Phase 6: Reshape Frontend
**Single app, 5 pages, no multi-tenant complexity.**
- Remove multi-tenant UI code (tenant selector, config system, setup routes)
- Delete pages: Settings, AuthCallback
- Simplify routing: Login, Register, Overview, Alerts, Events, Models
- Update API calls for new endpoints and event schema
- Remove WebSocket (use polling)
- Update auth context to remove tenant_id
- Update page components for behavior events (show user_identifier, event_type, source_ip, etc.)
- Commit: `feat: simplify dashboard for single-tenant use`

**Pages:**
- `/login` — LoginPage (remove org_name field)
- `/register` — RegisterPage
- `/overview` — Overview with KPIs and recent alerts
- `/alerts` — Filterable alert table
- `/events` — Behavior event table (user_identifier, event_type, source_ip, occurred_at)
- `/models` — Model training and status

---

## Execution Checklist

### Before Starting
- [ ] On `pivot/moal-ai` branch (already created)
- [ ] Understand the overengineering audit (read the architect report)
- [ ] Understand target user (security engineer, self-hosted, user behavior focus)
- [ ] Have LANL dataset reference (optional: for real training data)

### Phase 1: Rebrand
- [ ] Rename `risk_common/` directory to `moal_common/`
- [ ] Update all imports: `from risk_common` → `from moal_common`
- [ ] Update branding strings (aegis → moal-ai)
- [ ] Update README.md
- [ ] Commit and test: `python -c "import moal_common"` works

### Phase 2: Strip
- [ ] Delete 6 backend services
- [ ] Delete 2 frontend apps
- [ ] Delete dead code directories
- [ ] Delete infrastructure (K8s, reverse-proxy, postgres init)
- [ ] Delete unnecessary scripts
- [ ] Remove v1 routes and auth
- [ ] Simplify config.py
- [ ] Commit (accept worker is broken)

### Phase 3: Reshape Data
- [ ] Create Alembic migration
- [ ] Update ORM models
- [ ] Update Pydantic schemas
- [ ] Rewrite repositories
- [ ] Test migration: `alembic upgrade head`
- [ ] Commit

### Phase 4: ML Pipeline
- [ ] Implement feature_engineering.py
- [ ] Rewrite event ingestion endpoint
- [ ] Delete worker service
- [ ] Test: POST /api/events/ingest works
- [ ] Optional: Add LANL loader
- [ ] Commit

### Phase 5: Infrastructure
- [ ] Rewrite docker-compose.yml
- [ ] Simplify scripts
- [ ] Update CI pipeline
- [ ] Test: `docker compose up` starts 4 services
- [ ] Commit

### Phase 6: Frontend
- [ ] Remove multi-tenant code
- [ ] Simplify routing
- [ ] Update API calls
- [ ] Test: Dashboard loads and calls API
- [ ] Commit

### Final
- [ ] All tests pass
- [ ] `docker compose up` works end-to-end
- [ ] Create PR from `pivot/moal-ai` → main (for review before merge)

---

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Phase 1 rename breaks all imports | HIGH | Atomic find-and-replace, test imports immediately |
| Phase 2 makes worker non-functional | MEDIUM | Accepted — worker deleted in Phase 4 anyway |
| Phase 3 migration is destructive | MEDIUM | This is a pivot branch, not production. Document one-way migration. |
| ML autoencoder trained on noise | MEDIUM | Phase 4.6 provides LANL data for real training |
| Synchronous processing slower than async | LOW | Acceptable for self-hosted single-tenant; add queue later if needed |
| Frontend API mocks become stale | MEDIUM | Update mocks before updating real API calls |

---

## Success Criteria

- [ ] No `aegis` or `risk` references in user-facing strings
- [ ] Single FastAPI service handles auth, events, scoring, alerts
- [ ] Single React dashboard: 5 pages, no multi-tenant UI
- [ ] Database: ~5 tables (users, behavior_events, anomaly_results, alerts, model_registry)
- [ ] `docker compose up` starts 4 services only
- [ ] Event ingestion accepts behavior data with real feature columns
- [ ] Autoencoder trains/scores on real features, not hash noise
- [ ] No RabbitMQ, Redis, K8s, OAuth, or multi-tenancy
- [ ] All tests pass
- [ ] CI runs successfully on `pivot/moal-ai`

---

## Reference: Overengineering Audit Summary

### What Was Built
A production-grade distributed system for transaction fraud detection with:
- Multi-tenancy (tenant isolation, per-tenant config, domain management)
- Dual API versions (v1 legacy, v2 current)
- Three auth strategies (cookies, API keys, bearer tokens)
- OAuth (Google, Apple)
- Refresh token rotation with rotation detection
- Reference data enrichment (OFAC, FATF, FX rates, IP intelligence, BIN data)
- Rules engine with 8 configurable rules
- TensorFlow autoencoder for anomaly scoring
- Dedicated services for enrichment, metrics, notifications, alert routing
- Multi-user platform with tenant onboarding
- Kubernetes manifests with HPA autoscaling
- WebSocket live alerts
- Email/Slack/webhook delivery
- Model drift detection

### What's Actually Needed for MVP
- Single API service (auth + event ingestion + scoring)
- PostgreSQL database
- Dashboard for triage
- ML model (rules OR ML, not both)
- Self-hosted single-tenant (no multi-tenancy)

### The Gap
The actual product is 80% unnecessary infrastructure built to showcase skills, not solve a real problem for paying customers.

---

## Next Steps

1. **Review this plan** in a new chat session
2. **Start Phase 1** (rebrand) — low risk, good warmup
3. **Work through phases 2-6** in order, one commit per phase (or multiple commits within a phase if needed)
4. **Test after each phase** before moving to the next
5. **Create PR** from `pivot/moal-ai` → main when all phases complete

Good luck! 🚀
