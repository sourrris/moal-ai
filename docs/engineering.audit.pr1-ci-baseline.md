# PR1 Audit + CI Baseline Report

## Scope
- Repository health baseline for backend/frontend quality gates.
- Safe dependency floor bumps (minor/patch) in Python services.
- Initial dependency risk report with actionable follow-ups.

## Tooling status

### Automated audit execution in this environment
- `pip-audit` install was blocked by package index network policy (`403 Forbidden` through configured proxy).
- `npm audit` request was blocked by registry policy (`403 Forbidden` on advisory endpoint).

Because of those restrictions, this PR includes:
1. A CI-ready place to run dependency checks (`backend/requirements-dev.txt` includes `pip-audit`).
2. A manual-first risk review from existing manifests.

## Dependency posture review

### Python
- **fastapi / uvicorn / httpx / redis / numpy floor bumps** were applied to reduce exposure to older minors while staying non-breaking (`<1.0` or `<2.0` bounds preserved).
- **`passlib[bcrypt]`** is still present in `api_gateway`; library maintenance is limited and should be replaced with **argon2id** (`argon2-cffi`) in auth hardening PR.
- **No pinned transitive lockfiles** yet for Python services; reproducibility/security drift risk remains.

### Frontend
- Frontend currently installs without a committed lockfile; determinism risk remains and should be addressed in a follow-up PR.
- `npm audit` could not run in this environment, so security findings are deferred to CI execution in an unrestricted runner.

## Recommended follow-up actions
1. Add a scheduled dependency audit workflow (weekly) running `pip-audit` and `npm audit --audit-level=moderate`.
2. Introduce lockfile strategy for Python (`pip-tools`/`uv lock`) to control transitive supply chain drift.
3. Replace `passlib[bcrypt]` with `argon2-cffi` and rotate auth settings to `JWT_SECRET` + `JWT_REFRESH_SECRET` model.
4. Add SBOM generation (`syft`) and container image scanning (`trivy`) in CI.

## Environment variables to standardize in upcoming PRs
- `DATABASE_URL`
- `REDIS_URL`
- `SENTRY_DSN`
- `JWT_SECRET`
- `JWT_REFRESH_SECRET`
- `AUGUS_API_KEY`
