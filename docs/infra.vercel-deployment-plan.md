# Vercel Production Deployment Plan (Main -> `prod`)

## Branching
- Target runtime branch for deployment hardening: `prod`.
- Upstream merge target remains `main`.
- Strategy: implement deployment-safe changes in `prod`, validate, then open PR into `main`.

## Current State (What Already Works Locally)
The dashboard already supports local execution with Vite and has environment-variable based endpoints:
- Local app run: `npm run dev` (`frontend/dashboard`, port `5173`).
- Static build output: `frontend/dashboard/dist` via `npm run build`.
- API and WS URLs are already configurable via `VITE_*` values (with local defaults):
  - `VITE_API_BASE_URL` -> defaults to `http://api.localhost`
  - `VITE_WS_BASE_URL` -> defaults to `http://ws.localhost`
  - `VITE_CONTROL_TENANT_URL` -> defaults to `http://control.localhost`
  - `VITE_CONTROL_OPS_URL` -> defaults to `http://ops-control.localhost`

## Deployment Goal
Deploy `frontend/dashboard` to Vercel for `main` with no regressions to local development.

---

## Phase 1 — Baseline Vercel Project Wiring (No Runtime Behavior Changes)
1. Create Vercel project rooted at `frontend/dashboard`.
2. Set build and output explicitly:
   - Install command: `npm ci`
   - Build command: `npm run build`
   - Output directory: `dist`
3. Set production branch in Vercel to `main`.
4. Keep preview deployments enabled for non-main branches.

**Acceptance Criteria**
- Preview deploy succeeds from `prod`.
- Production deploy path is bound to `main` only.

## Phase 2 — Environment Variable Contract for Vercel
Add explicit Vercel environment variables (Preview + Production) so browser clients never rely on localhost defaults.

### Required
- `VITE_API_BASE_URL=https://<api-domain>`
- `VITE_WS_BASE_URL=https://<ws-domain>` (or wss-compatible gateway URL if required by platform routing)

### Optional (if control-plane frontends are public)
- `VITE_CONTROL_TENANT_URL=https://<control-tenant-domain>`
- `VITE_CONTROL_OPS_URL=https://<control-ops-domain>`

**Acceptance Criteria**
- Built assets in Vercel resolve API URLs to real hosted domains.
- No network calls in production point to `*.localhost`.

## Phase 3 — SPA Routing and Edge Rewrites
Because dashboard uses client-side routing, add a Vercel rewrite fallback:
- Route all non-asset paths to `/index.html`.

Recommended `vercel.json` (to be added in `frontend/dashboard` when implementing):
```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

**Acceptance Criteria**
- Deep links (e.g. `/alerts`, `/events`, `/models`) load directly without 404.

## Phase 4 — Production Safety and Validation Gates
Add a minimal deployment validation checklist in CI and release process:
1. `npm ci`
2. `npm run test`
3. `npm run build`
4. Validate asset output exists (`dist/index.html`, PWA assets).
5. Smoke test key pages after deploy (`/`, `/alerts`, `/events`).

**Acceptance Criteria**
- Vercel build artifacts are reproducible locally.
- Main-branch deploy is blocked if tests/build fail.

## Phase 5 — Local + Vercel Compatibility Guardrails
To preserve current local behavior while improving Vercel reliability:
1. Keep localhost defaults in code for local-only runs.
2. Add a production-time assertion (script/check) that fails if any `VITE_*` endpoint is missing when `NODE_ENV=production`.
3. Document a two-mode configuration matrix:
   - Local mode: defaults allowed.
   - Vercel mode: explicit env vars mandatory.

**Acceptance Criteria**
- Local developers can still run without extra setup.
- Production deploy cannot accidentally use localhost endpoints.

---

## Proposed Rollout Sequence
1. Configure Vercel project (manual setup).
2. Add `vercel.json` rewrite + env validation check (code/docs PR).
3. Validate preview on `prod`.
4. Merge to `main`.
5. Execute first production deploy from `main`.

## Risk Register and Mitigations
- **Risk:** Browser API calls fail due wrong base URL.
  - **Mitigation:** Mandatory `VITE_API_BASE_URL` and release smoke test.
- **Risk:** Deep-link 404 errors.
  - **Mitigation:** SPA rewrite in `vercel.json`.
- **Risk:** Local dev breaks after production hardening.
  - **Mitigation:** Preserve localhost defaults and separate local/prod rules.
- **Risk:** WebSocket connectivity differences in hosted edge.
  - **Mitigation:** Validate WS endpoint over TLS (`wss`) in preview before main deploy.

## Definition of Done
- `main` deploys successfully on Vercel.
- Dashboard routes deep-link safely.
- Production endpoints are non-localhost and documented.
- Local development flow remains unchanged.
