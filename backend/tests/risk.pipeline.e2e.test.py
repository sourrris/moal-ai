"""End-to-end pipeline tests for V2 event ingestion and V1/V2 worker processing."""

from __future__ import annotations

import json
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
from app.application.processor import EventProcessor
from app.infrastructure.db import get_db_session
from risk_common.schemas import InferenceResponse
from risk_common.schemas_v2 import AuthClaims


def _claims(tenant_id: str = "tenant-a", scopes: list[str] | None = None) -> AuthClaims:
    return AuthClaims(
        sub="test-user",
        tenant_id=tenant_id,
        roles=["analyst"],
        scopes=scopes if scopes is not None else ["events:write", "events:read"],
    )


def _event_body() -> dict:
    return {
        "source": "test-source",
        "event_type": "transaction",
        "occurred_at": datetime.now(UTC).isoformat(),
        "transaction": {
            "transaction_id": str(uuid4()),
            "amount": 100.0,
            "currency": "USD",
            "merchant_id": "merchant-1",
        },
    }


class _FakeSession:
    async def execute(self, stmt, params=None):
        return SimpleNamespace(scalar_one_or_none=lambda: None, first=lambda: None)

    async def commit(self):
        pass


class _FakeSessionCtx:
    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *_):
        pass


class _FakeRedis:
    def __init__(self, hit: bool = False):
        self.hit = hit
        self.stored: dict = {}

    async def get(self, key: str):
        return b"1" if self.hit else None

    async def set(self, key: str, value, ex=None):
        self.stored[key] = value


class _FakeMessage:
    def __init__(self, body: dict):
        self.body = json.dumps(body, default=str).encode()
        self.headers = {}
        self.acked = False

    async def ack(self):
        self.acked = True

    async def nack(self, requeue=False):
        pass


class _FakeInferenceResponse:
    def __init__(self, *, anomaly_score: float = 0.1, threshold: float = 0.5, is_anomaly: bool = False):
        self.event_id = uuid4()
        self.model_name = "risk_autoencoder"
        self.model_version = "v1"
        self.anomaly_score = anomaly_score
        self.threshold = threshold
        self.is_anomaly = is_anomaly


class _TestProcessor(EventProcessor):
    def __init__(self, redis, channel, *, inference: _FakeInferenceResponse):
        super().__init__(redis, channel)
        self._inference = inference

    async def _call_inference(self, event_id, transaction, features):
        return self._inference

    async def _resolve_tenant_config(self, tenant_id):
        return None

    async def _resolve_enrichment_v2(self, event):
        return {}, [], 0


def _ingest_app(session, claims: AuthClaims) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_events_v2.router)
    app.state.rabbit_channel = SimpleNamespace()

    async def _db():
        yield session

    async def _auth():
        return claims

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[deps.get_auth_claims] = _auth
    app.dependency_overrides[deps.get_rabbit_channel] = lambda: app.state.rabbit_channel
    return app


@pytest.mark.asyncio
async def test_v2_ingest_new_event_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    published: list = []

    async def fake_create_if_absent(_session, event):
        return True

    async def fake_persist_event(_session, envelope, *, submitted_by):
        pass

    async def fake_publish(**kwargs):
        published.append(kwargs)

    monkeypatch.setattr(routes_events_v2.EventV2Repository, "create_if_absent", fake_create_if_absent)
    monkeypatch.setattr(routes_events_v2.EventIngestionService, "persist_event", fake_persist_event)
    monkeypatch.setattr(routes_events_v2, "publish_json_with_compat", fake_publish)

    app = _ingest_app(_FakeSession(), _claims("tenant-a"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v2/events/ingest", json=_event_body())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["queued"] is True
    assert len(published) == 1


@pytest.mark.asyncio
async def test_v2_ingest_duplicate_event_skips_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    published: list = []

    async def fake_create_if_absent(_session, event):
        return False

    async def fake_publish(**kwargs):
        published.append(kwargs)

    monkeypatch.setattr(routes_events_v2.EventV2Repository, "create_if_absent", fake_create_if_absent)
    monkeypatch.setattr(routes_events_v2, "publish_json_with_compat", fake_publish)

    app = _ingest_app(_FakeSession(), _claims("tenant-a"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v2/events/ingest", json=_event_body())

    assert response.status_code == 200
    assert response.json()["status"] == "duplicate"
    assert response.json()["queued"] is False
    assert len(published) == 0


@pytest.mark.asyncio
async def test_v2_ingest_requires_write_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _ingest_app(_FakeSession(), _claims("tenant-a", scopes=["events:read"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v2/events/ingest", json=_event_body())

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_worker_v1_nonanomalous_event_acks_without_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.processor as processor_mod

    persisted: list = []
    published: list = []
    fake_session = _FakeSession()

    async def fake_persist_inference(session, *, event_id, model_name, model_version, score, threshold, is_anomaly):
        persisted.append({"event_id": event_id, "is_anomaly": is_anomaly})

    async def fake_publish(**kwargs):
        published.append(kwargs)

    monkeypatch.setattr(processor_mod, "SessionLocal", lambda: _FakeSessionCtx(fake_session))
    monkeypatch.setattr(processor_mod, "persist_inference", fake_persist_inference)
    monkeypatch.setattr(processor_mod, "publish_json_with_compat", fake_publish)

    inference = _FakeInferenceResponse(anomaly_score=0.1, threshold=0.5, is_anomaly=False)
    processor = _TestProcessor(_FakeRedis(hit=False), SimpleNamespace(), inference=inference)

    event_id = uuid4()
    body = {
        "event_id": str(event_id),
        "tenant_id": "tenant-a",
        "source": "test",
        "event_type": "transaction",
        "payload": {"amount": 100.0, "currency": "USD"},
        "features": [0.1] * 8,
        "occurred_at": datetime.now(UTC).isoformat(),
        "ingested_at": datetime.now(UTC).isoformat(),
    }
    message = _FakeMessage(body)
    await processor.handle_message(message)

    assert message.acked
    assert len(persisted) == 1
    assert persisted[0]["is_anomaly"] is False
    assert len(published) == 0


@pytest.mark.asyncio
async def test_worker_v1_anomalous_event_publishes_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.processor as processor_mod

    published: list = []
    fake_session = _FakeSession()

    async def fake_persist_inference(session, *, event_id, model_name, model_version, score, threshold, is_anomaly):
        pass

    async def fake_publish(**kwargs):
        published.append(kwargs)

    monkeypatch.setattr(processor_mod, "SessionLocal", lambda: _FakeSessionCtx(fake_session))
    monkeypatch.setattr(processor_mod, "persist_inference", fake_persist_inference)
    monkeypatch.setattr(processor_mod, "publish_json_with_compat", fake_publish)

    inference = _FakeInferenceResponse(anomaly_score=0.95, threshold=0.5, is_anomaly=True)
    processor = _TestProcessor(_FakeRedis(hit=False), SimpleNamespace(), inference=inference)

    body = {
        "event_id": str(uuid4()),
        "tenant_id": "tenant-a",
        "source": "test",
        "event_type": "transaction",
        "payload": {"amount": 100.0, "currency": "USD"},
        "features": [0.1] * 8,
        "occurred_at": datetime.now(UTC).isoformat(),
        "ingested_at": datetime.now(UTC).isoformat(),
    }
    message = _FakeMessage(body)
    await processor.handle_message(message)

    assert message.acked
    assert len(published) == 2


@pytest.mark.asyncio
async def test_worker_v1_dedup_hit_acks_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.processor as processor_mod

    called: list = []

    async def fake_persist_inference(**kwargs):
        called.append("persist")

    monkeypatch.setattr(processor_mod, "persist_inference", fake_persist_inference)

    inference = _FakeInferenceResponse()
    processor = _TestProcessor(_FakeRedis(hit=True), SimpleNamespace(), inference=inference)

    body = {
        "event_id": str(uuid4()),
        "tenant_id": "tenant-a",
        "source": "test",
        "event_type": "transaction",
        "payload": {},
        "features": [0.1] * 8,
        "occurred_at": datetime.now(UTC).isoformat(),
        "ingested_at": datetime.now(UTC).isoformat(),
    }
    message = _FakeMessage(body)
    await processor.handle_message(message)

    assert message.acked
    assert len(called) == 0


@pytest.mark.asyncio
async def test_worker_v2_dedup_hit_acks_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.processor as processor_mod

    called: list = []

    async def fake_persist_enrichment(*args, **kwargs):
        called.append("enrich")

    monkeypatch.setattr(processor_mod, "persist_enrichment", fake_persist_enrichment)

    inference = _FakeInferenceResponse()
    redis = _FakeRedis(hit=True)
    processor = _TestProcessor(redis, SimpleNamespace(), inference=inference)

    from risk_common.schemas_v2 import RiskEventV2
    event = RiskEventV2(
        tenant_id="tenant-a",
        source="test",
        event_type="transaction",
        transaction={
            "transaction_id": str(uuid4()),
            "amount": 50.0,
            "currency": "USD",
        },
        occurred_at=datetime.now(UTC),
        submitted_by="test",
    )
    body = event.model_dump(mode="json")
    message = _FakeMessage(body)
    await processor.handle_message_v2(message)

    assert message.acked
    assert len(called) == 0
