"""HTTP contract tests for /v1/models endpoints."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))
sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "risk" / "api"))

from app.api import deps, routes_models
from app.application.risk_event_service import ModelGatewayError
from app.infrastructure.db import get_db_session
from risk_common.schemas_v2 import AuthClaims


def _test_claims(read_only: bool = False) -> AuthClaims:
    scopes = ["models:read"] if read_only else ["models:read", "models:write"]
    return AuthClaims(sub="tester", tenant_id="tenant-alpha", scopes=scopes, roles=["admin"])


def _build_app(session_obj: object, claims: AuthClaims) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_models.router)

    async def _override_db():
        yield session_obj

    async def _override_claims():
        return claims

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[deps.get_auth_claims] = _override_claims
    return app


@pytest.mark.asyncio
async def test_get_models_contract_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace()
    app = _build_app(session, _test_claims(read_only=True))

    async def fake_get_active_model():
        return {
            "model_name": "risk_autoencoder",
            "model_version": "20260301000000",
            "feature_dim": 8,
            "threshold": 0.8,
        }

    async def fake_list_all_models():
        return [{"model_name": "risk_autoencoder", "model_version": "20260301000000", "threshold": 0.8}]

    async def fake_list_model_stats(_session):
        return [
            {
                "model_name": "risk_autoencoder",
                "model_version": "20260301000000",
                "threshold": "0.8",
                "updated_at": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
                "inference_count": "42",
                "anomaly_rate": "0.125",
            }
        ]

    monkeypatch.setattr(routes_models.ModelManagementService, "get_active_model", fake_get_active_model)
    monkeypatch.setattr(routes_models.ModelManagementService, "list_all_models", fake_list_all_models)
    monkeypatch.setattr(routes_models.ModelRepository, "list_models", fake_list_model_stats)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_model"]["model_version"] == "20260301000000"
    assert payload["items"][0]["activate_capable"] is True
    assert payload["items"][0]["source"] == "registry"


@pytest.mark.asyncio
async def test_train_models_contract_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace()
    app = _build_app(session, _test_claims())
    run_id = uuid4()
    finalized: dict[str, Any] = {}

    async def fake_create_training_run(_session, *, model_name, parameters, initiated_by):
        assert model_name == "risk_autoencoder"
        assert initiated_by == "tester"
        assert parameters["training_source"] == "historical_events"
        return run_id

    async def fake_fetch_training_features(_session, *, tenant_id, lookback_hours, max_samples):
        assert tenant_id == "tenant-alpha"
        assert lookback_hours == 24
        assert max_samples == 80
        return [[0.1, 0.2] for _ in range(80)]

    async def fake_get_active_model():
        return {
            "model_name": "risk_autoencoder",
            "model_version": "20260228000000",
            "feature_dim": 2,
            "threshold": 0.8,
        }

    async def fake_train_model(payload):
        assert payload["training_source"] == "provided_features"
        return {
            "model_name": "risk_autoencoder",
            "model_version": "20260301112233",
            "feature_dim": 2,
            "threshold": 0.9,
            "updated_at": "2026-03-01T11:22:33Z",
            "sample_count": 80,
            "auto_activated": False,
            "training_metrics": {
                "train_loss": 0.10,
                "val_loss": 0.12,
                "preprocessing": {"mean": [0.0, 0.0], "std": [1.0, 1.0]},
            },
        }

    async def fake_finalize_training_run(_session, *, run_id, status, model_version, metrics, parameters=None, notes=None):
        finalized.update(
            {
                "run_id": run_id,
                "status": status,
                "model_version": model_version,
                "metrics": metrics,
                "parameters": parameters,
                "notes": notes,
            }
        )

    monkeypatch.setattr(routes_models.ModelOpsRepository, "create_training_run", fake_create_training_run)
    monkeypatch.setattr(routes_models.ModelRepository, "fetch_training_features", fake_fetch_training_features)
    monkeypatch.setattr(routes_models.ModelManagementService, "get_active_model", fake_get_active_model)
    monkeypatch.setattr(routes_models.ModelManagementService, "train_model", fake_train_model)
    monkeypatch.setattr(routes_models.ModelOpsRepository, "finalize_training_run", fake_finalize_training_run)

    body = {
        "model_name": "risk_autoencoder",
        "training_source": "historical_events",
        "lookback_hours": 24,
        "max_samples": 80,
        "min_samples": 64,
        "epochs": 4,
        "batch_size": 16,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/models/train", json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == str(run_id)
    assert payload["status"] == "success"
    assert payload["model_version"] == "20260301112233"
    assert finalized["status"] == "success"
    assert finalized["metrics"]["preprocessing"]["std"] == [1.0, 1.0]


@pytest.mark.asyncio
async def test_activate_models_contract_not_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace()
    app = _build_app(session, _test_claims())

    async def fake_list_all_models():
        return [{"model_name": "risk_autoencoder", "model_version": "20260301000000"}]

    monkeypatch.setattr(routes_models.ModelManagementService, "list_all_models", fake_list_all_models)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/models/activate",
            json={"model_name": "risk_autoencoder", "model_version": "20260301999999"},
        )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "not_registry_model"


@pytest.mark.asyncio
async def test_activate_models_contract_artifact_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace()
    app = _build_app(session, _test_claims())

    async def fake_list_all_models():
        return [{"model_name": "risk_autoencoder", "model_version": "20260301000000", "threshold": 0.9}]

    async def fake_get_active_model():
        return {
            "model_name": "risk_autoencoder",
            "model_version": "20260228000000",
            "feature_dim": 8,
            "threshold": 1.0,
        }

    async def fake_get_run(_session, *, model_name, model_version):
        loss = 0.11 if model_version == "20260301000000" else 0.20
        return {
            "run_id": uuid4(),
            "model_name": model_name,
            "model_version": model_version,
            "status": "success",
            "started_at": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
            "finished_at": datetime(2026, 3, 1, 10, 10, tzinfo=UTC),
            "parameters": {"dataset_summary": {"effective_sample_count": 160}},
            "metrics": {"sample_count": 160, "val_loss": loss},
            "initiated_by": "tester",
        }

    async def fake_activate_model(_payload):
        raise ModelGatewayError(
            status_code=409,
            detail={"code": "artifact_missing", "message": "Model artifact file does not exist"},
        )

    monkeypatch.setattr(routes_models.ModelManagementService, "list_all_models", fake_list_all_models)
    monkeypatch.setattr(routes_models.ModelManagementService, "get_active_model", fake_get_active_model)
    monkeypatch.setattr(routes_models.ModelOpsRepository, "get_latest_successful_training_run", fake_get_run)
    monkeypatch.setattr(routes_models.ModelManagementService, "activate_model", fake_activate_model)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/models/activate",
            json={"model_name": "risk_autoencoder", "model_version": "20260301000000"},
        )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "artifact_missing"


@pytest.mark.asyncio
async def test_activate_models_contract_minimum_sample_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace()
    app = _build_app(session, _test_claims())

    async def fake_list_all_models():
        return [{"model_name": "risk_autoencoder", "model_version": "20260301000000", "threshold": 1.05}]

    async def fake_get_active_model():
        return {
            "model_name": "risk_autoencoder",
            "model_version": "20260228000000",
            "feature_dim": 8,
            "threshold": 1.0,
        }

    async def fake_get_run(_session, *, model_name, model_version):
        if model_version == "20260301000000":
            return {
                "run_id": uuid4(),
                "model_name": model_name,
                "model_version": model_version,
                "status": "success",
                "started_at": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
                "finished_at": datetime(2026, 3, 1, 10, 10, tzinfo=UTC),
                "parameters": {"dataset_summary": {"effective_sample_count": 40}},
                "metrics": {"sample_count": 40, "val_loss": 0.18},
                "initiated_by": "tester",
            }
        return {
            "run_id": UUID("11111111-1111-1111-1111-111111111111"),
            "model_name": model_name,
            "model_version": model_version,
            "status": "success",
            "started_at": datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
            "finished_at": datetime(2026, 3, 1, 8, 10, tzinfo=UTC),
            "parameters": {"dataset_summary": {"effective_sample_count": 120}},
            "metrics": {"sample_count": 120, "val_loss": 0.2},
            "initiated_by": "tester",
        }

    monkeypatch.setattr(routes_models.ModelManagementService, "list_all_models", fake_list_all_models)
    monkeypatch.setattr(routes_models.ModelManagementService, "get_active_model", fake_get_active_model)
    monkeypatch.setattr(routes_models.ModelOpsRepository, "get_latest_successful_training_run", fake_get_run)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/models/activate",
            json={"model_name": "risk_autoencoder", "model_version": "20260301000000"},
        )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_metadata"
    assert detail["minimum_samples"] == routes_models.ACTIVATION_MIN_SAMPLES
