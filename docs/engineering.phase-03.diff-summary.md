# Engineering Phase 03 Diff Summary

## Scope
Controlled renaming refactor applied across backend, frontend, docs, tests, Docker references, CI paths, and imports.

## Key Outcomes

- Backend service directories moved to `backend/services/risk/*`.
- Backend module names normalized away from generic naming.
- Frontend feature folders renamed to `{feature}.content`.
- Test files renamed to dotted `*.test.py` / `.test.tsx` conventions.
- Docker and CI references updated to renamed service paths.
- Protocol compatibility cutover implemented (RabbitMQ/Redis/WebSocket dual support).

## Validation

- Static compile and import validation: passed.
- FastAPI router mount and websocket route inventory: passed (including `/ws/risk-stream`, `/ws/stream`, `/ws/alerts`).
- Worker topology references and compatibility publish paths: passed static verification.
- Docker compose config: passed.
- Docker image build: blocked by unavailable Docker daemon in host environment.

## Runtime Impact

- No intentional feature/schema behavior change.
- Protocol naming migrated with staged compatibility to preserve existing integrations.
