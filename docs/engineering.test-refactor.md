# Engineering Test and Script Refactor

## Test Standardization

### Backend

- Renamed backend tests from `test_*.py` to dotted `*.test.py` format with import-safe underscores.
- Updated pytest collection config:
  - `python_files = ["test_*.py", "*.test.py"]`
  - `addopts = ["--import-mode=importlib"]`
- Preserved high-value test coverage for:
  - API contracts
  - Worker repository and processing paths
  - ML model training/serialization flows
  - Notification tenant routing

### Frontend

- Renamed tests to aligned names:
  - `ModelsEntity.test.tsx`
  - `WebSocketEntity.test.tsx`
  - `QueryLib.test.tsx`
  - Existing `ModelsPage.test.tsx` retained under renamed feature folder

## Script Standardization

Added standardized scripts:

- `scripts/dev.start.sh` -> wrapper for local stack start
- `scripts/dev.reset.sh` -> stop + setup + seed
- `scripts/dev.seed.sh` -> idempotent DB seed via `infra/postgres/init/001_schema.sql`
- `scripts/prod.build.sh` -> docker compose build wrapper

## Frontend Script Simplification

`frontend/dashboard/package.json` scripts now standardized to:

- `dev`
- `build`
- `test`
- `lint`

Removed non-standard script:

- `preview`

## Validation

- Backend: `pytest -q` => passed.
- Frontend: `npm run lint`, `npm test`, `npm run build` => passed.
