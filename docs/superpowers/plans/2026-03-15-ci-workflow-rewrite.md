# CI Workflow Rewrite Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `.github/workflows/ci.yml` from a single monolithic job into parallel, cached, well-scoped jobs that reflect the actual codebase structure.

**Architecture:** The current workflow runs all quality gates serially in one job (backend + frontend + infra + security + kustomize), making CI slow, hard to read, and unparallelizable. The rewrite splits this into 5 independent jobs (`security`, `backend-quality`, `frontend-quality`, `control-ops-smoke`, `infra-validate`) plus a `build` gate that depends on the quality jobs. Jobs that have no dependency on each other run in parallel.

**Tech Stack:** GitHub Actions, Python 3.11 + pip, Node 20 + npm, Docker Buildx, gitleaks-action v2, Trivy (pinned), Playwright, Kustomize (via kubectl)

---

## Chunk 1: Understand the current workflow's problems and plan the target state

### Task 1: Audit current workflow against codebase

**Files:**
- Read: `.github/workflows/ci.yml`
- Read: `pyproject.toml` (ruff/mypy/pytest config)
- Read: `backend/requirements-dev.txt`
- Read: `backend/services/risk/requirements.base.txt`
- Scan: `frontend/*/package.json` for npm scripts

- [ ] **Step 1: Note every problem with the current workflow**

  Current issues to fix:
  1. One monolithic `risk_api_quality_gate` job — security, Python deps, backend tests, migration, 3x Node installs, Playwright, and kustomize all run serially.
  2. No pip caching — reinstalls ~30 packages on every run.
  3. No npm caching — `npm install` (not `npm ci`) in 3 apps every run; `npm install` doesn't guarantee reproducibility.
  4. `trivy-action@master` — unstable ref, bad for supply-chain security.
  5. Gitleaks installed via `curl` with a hardcoded version in a run step — use the official action instead.
  6. `azure/setup-kubectl@v4` installed only to run `kubectl kustomize` — unnecessarily heavy.
  7. Docker builds (`risk_api_build_gate`) are **skipped on PRs** — Dockerfile regressions are only caught after merging to main.
  8. 30-minute timeout on a single job means any slow step blocks all downstream feedback.
  9. `ruff check backend/tests` only — should check full `backend/` (tests + services + libs) to catch regressions in service code too. (Current pyproject.toml ruff config applies to all Python files.)
  10. `mypy backend/tests` only — same issue, should check `backend/` broadly.

- [ ] **Step 2: Map out the target job dependency graph**

  ```
  security ─────────────────────────────────────────────────────────────────┐
  backend-quality (ruff, mypy, bandit, pip-audit, pytest, alembic) ─────────┤
  frontend-quality (vitest, tsc, vite build × 3 apps) ──────────────────────┼──► build (Docker + Trivy)
  control-ops-smoke (Playwright) — needs: frontend-quality ─────────────────┤
  infra-validate (kustomize overlays) ──────────────────────────────────────┘
  ```

  - `build` depends on ALL 5 quality jobs. This prevents pushing images to GHCR when kustomize overlays are broken or the Playwright smoke test fails — both make the images undeployable.
  - `control-ops-smoke` depends only on `frontend-quality` (Playwright needs the app built, not backend).
  - `infra-validate` has no dependencies — just `kubectl kustomize`.
  - All quality jobs run in parallel on every PR and on push to `main`, `work`, `upgrade/**`.

---

## Chunk 2: Write the new workflow

### Task 2: Replace `.github/workflows/ci.yml`

**Files:**
- Modify: `.github/workflows/ci.yml` — full replacement

- [ ] **Step 1: Back up the current workflow**

  ```bash
  cp .github/workflows/ci.yml .github/workflows/ci.yml.bak
  ```

- [ ] **Step 2: Write the new workflow**

  Replace `.github/workflows/ci.yml` with the following content exactly:

  ```yaml
  name: CI

  on:
    pull_request:
    push:
      branches: [main, work, "upgrade/**"]

  jobs:
    # ── 1. Secret / supply-chain scan ──────────────────────────────────────────
    security:
      name: security-scan
      runs-on: ubuntu-latest
      timeout-minutes: 10
      permissions:
        contents: read
      steps:
        - uses: actions/checkout@v4
          with:
            fetch-depth: 0

        - name: Gitleaks secret scan
          uses: gitleaks/gitleaks-action@v2
          env:
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            # GITLEAKS_NOGIT preserves --no-git semantics from the previous curl-based
            # install: scans the filesystem only, not git history. This avoids false
            # positives from already-rotated historical secrets. Remove this env var
            # only after populating a .gitleaksignore with any known historical findings.
            GITLEAKS_NOGIT: "true"

    # ── 2. Python quality gate ─────────────────────────────────────────────────
    backend-quality:
      name: backend-quality
      runs-on: ubuntu-latest
      timeout-minutes: 20
      permissions:
        contents: read
      services:
        postgres:
          image: postgres:16
          env:
            POSTGRES_USER: postgres
            POSTGRES_PASSWORD: postgres
            POSTGRES_DB: risk_monitor
          ports:
            - 5432:5432
          options: >-
            --health-cmd="pg_isready -U postgres -d risk_monitor"
            --health-interval=10s
            --health-timeout=5s
            --health-retries=5
      steps:
        - uses: actions/checkout@v4

        - uses: actions/setup-python@v5
          with:
            python-version: "3.11"
            cache: pip
            cache-dependency-path: |
              backend/libs/common/pyproject.toml
              backend/services/risk/requirements.base.txt
              backend/services/risk/**/requirements.txt
              backend/requirements-dev.txt

        - name: Install backend dependencies
          run: |
            set -euo pipefail
            python -m pip install --upgrade pip
            python -m pip install -e backend/libs/common
            while IFS= read -r req; do
              echo "Installing $req"
              python -m pip install -r "$req"
            done < <(find backend/services -name requirements.txt | sort)
            python -m pip install -r backend/requirements-dev.txt

        - name: Lint and type-check
          run: |
            ruff check backend/
            mypy backend/

        - name: Security audit
          run: |
            bandit -r backend/services backend/libs -q --severity-level medium
            # Audit all packages in the environment (no -r flag): the install step
            # already loaded every service requirement into this venv, so this scans
            # the full production + dev surface — fastapi, uvicorn, sqlalchemy, asyncpg,
            # tensorflow, passlib, slowapi, argon2-cffi, and all transitive deps.
            pip-audit --skip-editable -q

        - name: Run tests
          run: pytest -q

        - name: Validate migrations
          run: |
            cd backend
            DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/risk_monitor \
              alembic -c alembic.ini upgrade head

    # ── 3. Frontend quality gate ───────────────────────────────────────────────
    frontend-quality:
      name: frontend-quality
      runs-on: ubuntu-latest
      timeout-minutes: 15
      permissions:
        contents: read
      steps:
        - uses: actions/checkout@v4

        - uses: actions/setup-node@v4
          with:
            node-version: "20"
            cache: npm
            cache-dependency-path: |
              frontend/dashboard/package-lock.json
              frontend/control-tenant/package-lock.json
              frontend/control-ops/package-lock.json

        - name: Install frontend dependencies
          run: |
            npm ci --prefix frontend/dashboard
            npm ci --prefix frontend/control-tenant
            npm ci --prefix frontend/control-ops

        - name: Test and build
          run: |
            npm test --prefix frontend/dashboard
            npm run build --prefix frontend/dashboard
            npm test --prefix frontend/control-tenant
            npm run lint --prefix frontend/control-tenant
            npm run build --prefix frontend/control-tenant
            npm run lint --prefix frontend/control-ops
            npm run build --prefix frontend/control-ops

    # ── 4. Playwright smoke test (control-ops) ─────────────────────────────────
    control-ops-smoke:
      name: control-ops-smoke
      runs-on: ubuntu-latest
      timeout-minutes: 10
      needs: [frontend-quality]
      permissions:
        contents: read
      steps:
        - uses: actions/checkout@v4

        - uses: actions/setup-node@v4
          with:
            node-version: "20"
            cache: npm
            cache-dependency-path: frontend/control-ops/package-lock.json

        - name: Install dependencies
          run: npm ci --prefix frontend/control-ops

        - name: Install Playwright browser
          run: npx --prefix frontend/control-ops playwright install --with-deps chromium

        - name: Smoke test
          run: |
            set -euo pipefail
            cd frontend/control-ops
            npm run dev -- --host 127.0.0.1 --port 4175 >/tmp/control-ops.log 2>&1 &
            server_pid=$!
            trap 'kill "${server_pid}" >/dev/null 2>&1 || true' EXIT
            timeout 60 bash -c 'until curl -fsS http://127.0.0.1:4175 >/dev/null; do sleep 1; done'
            PLAYWRIGHT_BASE_URL=http://127.0.0.1:4175 npm run test:e2e

    # ── 5. Infrastructure validation ───────────────────────────────────────────
    infra-validate:
      name: infra-validate
      runs-on: ubuntu-latest
      timeout-minutes: 5
      permissions:
        contents: read
      steps:
        - uses: actions/checkout@v4

        - uses: azure/setup-kubectl@v4

        - name: Validate kustomize overlays
          run: |
            kubectl kustomize infra/eks/overlays/staging > /dev/null
            kubectl kustomize infra/eks/overlays/prod > /dev/null

    # ── 6. Docker build + push + scan ──────────────────────────────────────────
    build:
      name: build
      runs-on: ubuntu-latest
      timeout-minutes: 30
      needs: [security, backend-quality, frontend-quality, control-ops-smoke, infra-validate]
      permissions:
        contents: read
        packages: write
        security-events: write
      steps:
        - uses: actions/checkout@v4

        - name: Set up Docker Buildx
          uses: docker/setup-buildx-action@v3

        - name: Log in to GHCR
          if: github.ref == 'refs/heads/main'
          uses: docker/login-action@v3
          with:
            registry: ghcr.io
            username: ${{ github.actor }}
            password: ${{ secrets.GITHUB_TOKEN }}

        - name: Build (and push on main) service images
          env:
            PUSH: ${{ github.ref == 'refs/heads/main' && 'true' || 'false' }}
          run: |
            set -euo pipefail
            SHORT_SHA="${GITHUB_SHA::8}"
            build_and_push() {
              local tag="$1"
              local dockerfile="$2"
              local full_tag="ghcr.io/${GITHUB_REPOSITORY,,}/${tag}:${SHORT_SHA}"
              docker build -t "${full_tag}" -f "${dockerfile}" .
              if [ "${PUSH}" = "true" ]; then
                docker push "${full_tag}"
                docker tag "${full_tag}" "ghcr.io/${GITHUB_REPOSITORY,,}/${tag}:latest"
                docker push "ghcr.io/${GITHUB_REPOSITORY,,}/${tag}:latest"
              fi
            }
            while IFS= read -r dockerfile; do
              svc="$(basename "$(dirname "${dockerfile}")")"
              build_and_push "${svc}" "${dockerfile}"
            done < <(find backend/services -name Dockerfile | sort)
            build_and_push "migrations" "backend/Dockerfile.migrations"
            build_and_push "dashboard" "frontend/dashboard/Dockerfile"
            build_and_push "control-tenant" "frontend/control-tenant/Dockerfile"
            build_and_push "control-ops" "frontend/control-ops/Dockerfile"

        - name: Trivy vulnerability scan
          uses: aquasecurity/trivy-action@0.28.0
          with:
            scan-type: fs
            scan-ref: .
            severity: HIGH,CRITICAL
            exit-code: 1
            ignore-unfixed: true
  ```

- [ ] **Step 3: Delete the backup**

  ```bash
  rm .github/workflows/ci.yml.bak
  ```

- [ ] **Step 4: Commit the new workflow on the PR branch**

  ```bash
  # Must be on fix/6-bugs-audit or a new branch
  git add .github/workflows/ci.yml
  git commit -m "ci: rewrite workflow with parallel jobs and caching"
  git push
  ```

- [ ] **Step 5: Watch the CI run**

  ```bash
  gh run watch
  ```

  Expected: All 5 quality jobs run in parallel. `build` starts after `security + backend-quality + frontend-quality` pass. Green across the board.

  If any job fails, check logs with:
  ```bash
  gh run view --log-failed
  ```

---

## Chunk 3: Verification and cleanup

### Task 3: Validate each job's behaviour

**Files:**
- Read: `.github/workflows/ci.yml` (final version)

- [ ] **Step 1: Confirm parallel jobs ran concurrently**

  Run:
  ```bash
  gh run view <run-id> --json jobs | jq '.jobs[] | {name, startedAt, completedAt, conclusion}'
  ```

  Expected: `security`, `backend-quality`, `frontend-quality`, and `infra-validate` all have overlapping `startedAt` / `completedAt` timestamps.

- [ ] **Step 2: Confirm pip cache is working on second run**

  Trigger a second CI run (e.g. empty commit) and check the `backend-quality` job log. Expected: The `Install backend dependencies` step shows `Cache hit` or completes in under 30 seconds.

  ```bash
  git commit --allow-empty -m "ci: trigger cache warm-up run" && git push
  gh run watch
  ```

- [ ] **Step 3: Confirm npm cache is working**

  In the `frontend-quality` job log, the `Install frontend dependencies` step should show `npm ci` completing in under 30 seconds on the second run (cache hit).

- [ ] **Step 4: Confirm Docker builds run on PRs**

  Open a test PR (or use the existing `fix/6-bugs-audit` PR). Verify the `build` job runs and the images are built but NOT pushed (since it's not a main push).

  ```bash
  gh pr checks <pr-number>
  ```

  Expected: `build` shows as passed.

- [ ] **Step 5: Merge the PR**

  Once all checks are green on `fix/6-bugs-audit`:
  ```bash
  gh pr merge 14 --squash
  ```

---

## Summary of changes

| What | Before | After |
|------|--------|-------|
| Job structure | 1 monolithic job (quality) + 1 build | 5 parallel jobs + 1 build |
| Gitleaks | `curl` install, hardcoded v8.24.2 | `gitleaks/gitleaks-action@v2` |
| pip | No cache, full reinstall every run | `cache: pip` via setup-python |
| npm | `npm install` (no lock guarantee) | `npm ci` + `cache: npm` |
| Trivy | `@master` (unstable ref) | `@0.28.0` (pinned) |
| Docker on PRs | Skipped (build gate blocked by `needs` + push condition) | Always built, only pushed on main |
| Timeout | 30 min single job | Per-job timeouts (5–20 min) |
| Ruff scope | `backend/tests` only | `backend/` (full) |
| mypy scope | `backend/tests` only | `backend/` (full) |
| pip-audit | Installed but never invoked | Runs in `backend-quality` security audit step |
| Gitleaks mode | `--no-git` (filesystem only) | `GITLEAKS_NOGIT=true` (preserves filesystem-only) |
| build gate | `security + backend-quality + frontend-quality` | All 5 quality jobs (blocks push if smoke/infra broken) |
