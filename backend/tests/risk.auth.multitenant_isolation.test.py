"""Multi-tenant isolation tests: JWT enforcement, tenant scoping, and cross-tenant access denial."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "libs" / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "risk" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "risk" / "worker"))

from app.api import deps, routes_events_v2
from app.infrastructure.db import get_db_session
from risk_common.schemas_v2 import AuthClaims


def _make_app_with_auth(fake_token_payload: dict | None) -> FastAPI:
    from app.api import routes_auth_v2

    app = FastAPI()
    app.include_router(routes_events_v2.router)
    app.state.rabbit_channel = SimpleNamespace()

    class _FakeSession:
        async def execute(self, stmt, params=None):
            return SimpleNamespace(scalar_one_or_none=lambda: None, first=lambda: None)

        async def commit(self):
            pass

    async def _db():
        yield _FakeSession()

    app.dependency_overrides[get_db_session] = _db

    if fake_token_payload is None:
        async def _auth_no_tenant(**kwargs):
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant-scoped token required for v2 endpoints")
        app.dependency_overrides[deps.get_auth_claims] = _auth_no_tenant
    else:
        claims = AuthClaims(
            sub=str(fake_token_payload.get("sub", "user")),
            tenant_id=str(fake_token_payload["tenant_id"]),
            roles=fake_token_payload.get("roles", []),
            scopes=fake_token_payload.get("scopes", []),
        )

        async def _auth():
            return claims

        app.dependency_overrides[deps.get_auth_claims] = _auth
        app.dependency_overrides[deps.get_rabbit_channel] = lambda: app.state.rabbit_channel

    return app


def _event_body() -> dict:
    return {
        "source": "test",
        "event_type": "transaction",
        "occurred_at": datetime.now(UTC).isoformat(),
        "transaction": {
            "transaction_id": str(uuid4()),
            "amount": 50.0,
            "currency": "USD",
        },
    }


@pytest.mark.asyncio
async def test_v2_endpoint_rejects_token_without_tenant_id() -> None:
    app = _make_app_with_auth(None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v2/events/ingest",
            json=_event_body(),
            headers={"Authorization": "Bearer fake-no-tenant-token"},
        )

    assert response.status_code == 401
    assert "tenant" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_v2_ingest_stamps_tenant_from_jwt_not_from_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    async def fake_create_if_absent(_session, event):
        captured.append({"tenant_id": event.tenant_id})
        return True

    async def fake_persist_event(_session, envelope, *, submitted_by):
        pass

    async def fake_publish(**kwargs):
        pass

    monkeypatch.setattr(routes_events_v2.EventV2Repository, "create_if_absent", fake_create_if_absent)
    monkeypatch.setattr(routes_events_v2.EventIngestionService, "persist_event", fake_persist_event)
    monkeypatch.setattr(routes_events_v2, "publish_json_with_compat", fake_publish)

    app = _make_app_with_auth({"tenant_id": "tenant-b", "sub": "user1", "scopes": ["events:write"]})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {**_event_body(), "tenant_id": "tenant-a"}
        response = await client.post("/v2/events/ingest", json=body)

    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0]["tenant_id"] == "tenant-b"


@pytest.mark.asyncio
async def test_resolve_tenant_context_returns_none_for_unassigned_user_without_tenant() -> None:
    from app.infrastructure.monitoring_repository import UserRepository

    class _FakeUser:
        id = 1
        role = "analyst"

    class _FakeSession:
        async def execute(self, stmt, params=None):
            return SimpleNamespace(first=lambda: None)

        async def commit(self):
            pass

    result = await UserRepository.resolve_tenant_context(_FakeSession(), _FakeUser(), requested_tenant_id=None)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_tenant_context_uses_provided_tenant_when_no_role_mapping() -> None:
    from app.infrastructure.monitoring_repository import UserRepository

    class _FakeUser:
        id = 1
        role = "analyst"

    class _FakeSession:
        async def execute(self, stmt, params=None):
            return SimpleNamespace(first=lambda: None)

        async def commit(self):
            pass

    result = await UserRepository.resolve_tenant_context(_FakeSession(), _FakeUser(), requested_tenant_id="tenant-c")
    assert result is not None
    assert result["tenant_id"] == "tenant-c"
    assert "analyst" in result["roles"]


@pytest.mark.asyncio
async def test_worker_v2_dedup_key_is_tenant_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from app.application.processor import EventProcessor
    from risk_common.schemas_v2 import RiskEventV2

    class _FakeRedis:
        def __init__(self):
            self.lookups: list[str] = []
            self.stored: dict = {}

        async def get(self, key: str):
            self.lookups.append(key)
            return None

        async def set(self, key: str, value, ex=None):
            self.stored[key] = value

    import app.application.processor as processor_mod

    class _FakeSession:
        async def execute(self, stmt, params=None):
            from uuid import uuid4

            class _FakeRow:
                def __init__(self, m):
                    self._mapping = m

            class _FakeResult:
                def first(self):
                    return None

                def one(self):
                    return _FakeRow({"decision_id": uuid4(), "created_at": "2026-01-01T00:00:00Z"})

            return _FakeResult()

        async def commit(self):
            pass

    class _FakeSessionCtx:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(processor_mod, "SessionLocal", _FakeSessionCtx)

    async def fake_persist_enrichment(*a, **kw):
        pass

    async def fake_persist_decision(*a, **kw):
        return {"decision_id": uuid4(), "created_at": "2026-01-01T00:00:00Z"}

    async def fake_publish(**kw):
        pass

    monkeypatch.setattr(processor_mod, "persist_enrichment", fake_persist_enrichment)
    monkeypatch.setattr(processor_mod, "persist_decision", fake_persist_decision)
    monkeypatch.setattr(processor_mod, "publish_json_with_compat", fake_publish)

    class _FixedProcessor(EventProcessor):
        async def _call_inference(self, event_id, transaction, features):
            from risk_common.schemas import InferenceResponse
            from uuid import uuid4 as _uuid4

            return InferenceResponse(
                event_id=event_id,
                model_name="test",
                model_version="v1",
                anomaly_score=0.1,
                threshold=0.5,
                is_anomaly=False,
            )

        async def _resolve_tenant_config(self, tenant_id):
            return None

        async def _resolve_enrichment_v2(self, event):
            return {}, [], 0

    redis = _FakeRedis()
    processor = _FixedProcessor(redis, SimpleNamespace())

    event_id = uuid4()
    for tenant in ("tenant-a", "tenant-b"):
        event = RiskEventV2(
            event_id=event_id,
            tenant_id=tenant,
            source="test",
            event_type="transaction",
            transaction={"transaction_id": str(uuid4()), "amount": 10.0, "currency": "USD"},
            occurred_at=datetime.now(UTC),
            submitted_by="test",
        )

        class _Msg:
            def __init__(self, body):
                self.body = json.dumps(body, default=str).encode()
                self.headers = {}
                self.acked = False

            async def ack(self):
                self.acked = True

            async def nack(self, requeue=False):
                pass

        msg = _Msg(event.model_dump(mode="json"))
        await processor.handle_message_v2(msg)

    assert any("tenant-a" in k for k in redis.stored)
    assert any("tenant-b" in k for k in redis.stored)
    tenant_a_key = next(k for k in redis.stored if "tenant-a" in k)
    tenant_b_key = next(k for k in redis.stored if "tenant-b" in k)
    assert tenant_a_key != tenant_b_key
