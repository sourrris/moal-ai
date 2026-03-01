# Aegis AI Production Upgrade Plan

This document is the execution plan to move the current MVP toward a secure, scalable production platform in small, reviewable PRs.

## Principles
- Incremental, backward-compatible changes.
- PRs sized for <30 minute review.
- Secrets from environment variables only.
- Zero-downtime approach for all database changes.

## PR roadmap

### PR1 — Audit + CI baseline ✅
- Add CI jobs (lint, tests, type checks, image build).
- Add dependency audit notes and safe dependency floor bumps.

### PR2 — Auth and config hardening baseline (this PR) ✅
- Add standard env documentation (`.env.example`).
- Harden password handling to support argon2 hash upgrades on login.
- Remove plaintext default admin seed and use hashed seed via `pgcrypto`.
- Add unit tests for hash verification and legacy-password migration path.

### PR3 — DB migration baseline (Alembic)
- Add Alembic init and baseline migration from current schema.
- Document migration + rollback runbooks.
- Acceptance: `alembic upgrade head` and downgrade in CI.

### PR4 — JWT refresh + RBAC enforcement
- Add refresh token flow (`JWT_REFRESH_SECRET`) with rotation.
- Enforce role checks and tenant claim usage in API dependencies.
- Acceptance: auth integration tests including refresh/revoke path.

### PR5 — Tenant isolation end-to-end
- Add `tenant_id` enforcement and avoid caller-controlled tenant filters.
- Add DB constraints/indexes tuned for tenant queries.
- Acceptance: cross-tenant data access tests fail by default.

### PR6 — Workers, idempotency, and retries hardening
- Introduce explicit retry backoff policy and idempotency store pattern.
- Add dead-letter replay tooling and queue observability.
- Acceptance: deterministic retry/idempotency test scenarios.

### PR7 — Observability + deployment hardening
- Add Prometheus metrics endpoint and Sentry integration stubs (`SENTRY_DSN`).
- Add Kubernetes/Helm baseline with readiness/liveness probes and HPA guidance.
- Acceptance: deployment docs with canary CI/CD workflow.

## Environment variable standardization
Required production env variables:
- `DATABASE_URL`
- `REDIS_URL`
- `RABBITMQ_URL`
- `JWT_SECRET`
- `JWT_REFRESH_SECRET`
- `SENTRY_DSN`
- `AUGUS_API_KEY`
