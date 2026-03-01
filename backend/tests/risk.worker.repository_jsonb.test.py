"""Regression tests for JSONB serialization in v2 worker repositories."""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

worker_repo_path = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "risk"
    / "worker"
    / "app"
    / "infrastructure"
    / "event_repository_v2.py"
)
spec = importlib.util.spec_from_file_location("risk_worker_event_repository_v2", worker_repo_path)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load worker repository module")
repository_v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository_v2)


class _FakeRow:
    def __init__(self, mapping):
        self._mapping = mapping


class _FakeResult:
    def __init__(self, mapping=None):
        self._mapping = mapping or {}

    def one(self):
        return _FakeRow(self._mapping)


class _FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.commits = 0

    async def execute(self, stmt, params):
        sql = getattr(stmt, "text", str(stmt))
        self.calls.append((sql, params))
        if "RETURNING decision_id" in sql:
            return _FakeResult({"decision_id": uuid4(), "created_at": "2026-03-01T10:00:00Z"})
        return _FakeResult()

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_persist_enrichment_casts_and_serializes_jsonb_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_set_tenant_context(session, tenant_id):
        return None

    monkeypatch.setattr(repository_v2, "set_tenant_context", fake_set_tenant_context)
    session = _FakeSession()

    await repository_v2.persist_enrichment(
        session,
        tenant_id="tenant-alpha",
        event_id=uuid4(),
        sources=[],
        enrichment_payload={"provider": "ofac", "matches": 0},
        match_confidence=0.0,
        enrichment_latency_ms=15,
    )

    sql, params = session.calls[0]
    assert "CAST(:sources AS JSONB)" in sql
    assert "CAST(:enrichment_payload AS JSONB)" in sql
    assert json.loads(params["sources"]) == []
    assert json.loads(params["enrichment_payload"]) == {"provider": "ofac", "matches": 0}


@pytest.mark.asyncio
async def test_persist_decision_casts_and_serializes_decision_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_set_tenant_context(session, tenant_id):
        return None

    monkeypatch.setattr(repository_v2, "set_tenant_context", fake_set_tenant_context)
    session = _FakeSession()

    payload = {"rules": ["velocity"], "score_components": {"ml": 0.4}}
    await repository_v2.persist_decision(
        session,
        tenant_id="tenant-alpha",
        event_id=uuid4(),
        risk_score=0.42,
        risk_level="low",
        reasons=["ml_score_low"],
        rule_hits=["velocity"],
        model_name="risk_autoencoder",
        model_version="20260301000000",
        ml_anomaly_score=0.04,
        ml_threshold=0.9,
        decision_latency_ms=8,
        feature_vector=[0.1, 0.2],
        decision_payload=payload,
    )

    insert_sql, insert_params = session.calls[0]
    assert "CAST(:decision_payload AS JSONB)" in insert_sql
    assert json.loads(insert_params["decision_payload"]) == payload
    assert session.commits == 1
