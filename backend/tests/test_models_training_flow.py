"""Training flow behavior tests for models endpoints."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))
sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "api_gateway"))

from app.api import routes_models
from risk_common.schemas import ModelTrainRequest
from risk_common.schemas_v2 import AuthClaims


@pytest.mark.asyncio
async def test_train_model_records_success_run(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    captured: dict[str, Any] = {}
    claims = AuthClaims(sub="tester", tenant_id="tenant-alpha", scopes=["models:write", "models:read"])
    session = SimpleNamespace()

    async def fake_create_training_run(session_arg, *, model_name, parameters, initiated_by):
        captured["created"] = {
            "model_name": model_name,
            "parameters": parameters,
            "initiated_by": initiated_by,
            "session": session_arg,
        }
        return run_id

    async def fake_fetch_training_features(session_arg, *, tenant_id, lookback_hours, max_samples):
        assert session_arg is session
        assert tenant_id == "tenant-alpha"
        assert lookback_hours == 24
        assert max_samples == 96
        return [[0.1, 0.2] for _ in range(96)]

    async def fake_get_active_model():
        return {
            "model_name": "risk_autoencoder",
            "model_version": "20260228000000",
            "feature_dim": 2,
            "threshold": 0.8,
        }

    async def fake_train_model(payload):
        captured["train_payload"] = payload
        return {
            "model_name": "risk_autoencoder",
            "model_version": "20260301093000",
            "feature_dim": 2,
            "threshold": 0.9,
            "updated_at": "2026-03-01T09:30:00Z",
            "sample_count": 96,
            "auto_activated": False,
            "training_metrics": {"train_loss": 0.1, "val_loss": 0.2},
        }

    async def fake_finalize_training_run(session_arg, *, run_id, status, model_version, metrics, parameters=None, notes=None):
        captured["finalized"] = {
            "run_id": run_id,
            "status": status,
            "model_version": model_version,
            "metrics": metrics,
            "parameters": parameters,
            "notes": notes,
            "session": session_arg,
        }

    monkeypatch.setattr(routes_models.ModelOpsRepository, "create_training_run", fake_create_training_run)
    monkeypatch.setattr(routes_models.ModelRepository, "fetch_training_features", fake_fetch_training_features)
    monkeypatch.setattr(routes_models.ModelManagementService, "get_active_model", fake_get_active_model)
    monkeypatch.setattr(routes_models.ModelManagementService, "train_model", fake_train_model)
    monkeypatch.setattr(routes_models.ModelOpsRepository, "finalize_training_run", fake_finalize_training_run)

    response = await routes_models.train_model(
        ModelTrainRequest(
            model_name="risk_autoencoder",
            training_source="historical_events",
            lookback_hours=24,
            max_samples=96,
            min_samples=64,
            epochs=4,
            batch_size=16,
            threshold_quantile=0.99,
            auto_activate=False,
        ),
        claims,
        session,
    )

    assert response.run_id == run_id
    assert response.status == "success"
    assert response.model_version == "20260301093000"
    assert response.sample_count == 96
    assert response.metrics["baseline_comparison"]["active_model_version"] == "20260228000000"

    assert captured["created"]["parameters"]["training_source"] == "historical_events"
    assert captured["finalized"]["status"] == "success"
    assert captured["finalized"]["model_version"] == "20260301093000"
    assert captured["train_payload"]["training_source"] == "provided_features"


@pytest.mark.asyncio
async def test_train_model_records_failed_run_when_ml_training_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    captured: dict[str, Any] = {}
    claims = AuthClaims(sub="tester", tenant_id="tenant-alpha", scopes=["models:write", "models:read"])
    session = SimpleNamespace()

    async def fake_create_training_run(session_arg, *, model_name, parameters, initiated_by):
        return run_id

    async def fake_fetch_training_features(session_arg, *, tenant_id, lookback_hours, max_samples):
        return [[0.1, 0.2] for _ in range(80)]

    async def fake_train_model(payload):
        raise RuntimeError("downstream ml error")

    async def fake_finalize_training_run(session_arg, *, run_id, status, model_version, metrics, parameters=None, notes=None):
        captured["status"] = status
        captured["metrics"] = metrics
        captured["model_version"] = model_version
        captured["notes"] = notes

    monkeypatch.setattr(routes_models.ModelOpsRepository, "create_training_run", fake_create_training_run)
    monkeypatch.setattr(routes_models.ModelRepository, "fetch_training_features", fake_fetch_training_features)
    monkeypatch.setattr(routes_models.ModelManagementService, "train_model", fake_train_model)
    async def fake_get_active_model_none():
        return None

    monkeypatch.setattr(routes_models.ModelManagementService, "get_active_model", fake_get_active_model_none)
    monkeypatch.setattr(routes_models.ModelOpsRepository, "finalize_training_run", fake_finalize_training_run)

    with pytest.raises(HTTPException) as exc:
        await routes_models.train_model(
            ModelTrainRequest(
                model_name="risk_autoencoder",
                training_source="historical_events",
                lookback_hours=24,
                max_samples=80,
                min_samples=64,
                epochs=4,
                batch_size=16,
            ),
            claims,
            session,
        )

    assert exc.value.status_code == 502
    assert captured["status"] == "failed"
    assert captured["model_version"] is None
    assert "downstream ml error" in captured["notes"]


@pytest.mark.asyncio
async def test_list_models_marks_db_only_rows_as_inference_only(monkeypatch: pytest.MonkeyPatch) -> None:
    claims = AuthClaims(sub="tester", tenant_id="tenant-alpha", scopes=["models:read"])
    session = SimpleNamespace()

    async def fake_get_active_model():
        return {
            "model_name": "risk_autoencoder",
            "model_version": "20260301000000",
            "feature_dim": 2,
            "threshold": 0.8,
        }

    async def fake_list_all_models():
        return []

    async def fake_list_model_stats(session_arg):
        return [
            {
                "model_name": "risk_autoencoder",
                "model_version": "20260225000000",
                "threshold": "0.901",
                "inference_count": "22",
                "anomaly_rate": "0E-20",
            }
        ]

    monkeypatch.setattr(routes_models.ModelManagementService, "get_active_model", fake_get_active_model)
    monkeypatch.setattr(routes_models.ModelManagementService, "list_all_models", fake_list_all_models)
    monkeypatch.setattr(routes_models.ModelRepository, "list_models", fake_list_model_stats)

    result = await routes_models.list_models(claims, session)
    assert result.items
    only_row = result.items[0]
    assert only_row.source == "inference_only"
    assert only_row.activate_capable is False
    assert only_row.anomaly_rate == 0.0


@pytest.mark.asyncio
async def test_activate_model_rejects_non_registry_models(monkeypatch: pytest.MonkeyPatch) -> None:
    claims = AuthClaims(sub="tester", tenant_id="tenant-alpha", scopes=["models:write"])

    async def fake_list_all_models():
        return [{"model_name": "risk_autoencoder", "model_version": "20260301000000"}]

    monkeypatch.setattr(routes_models.ModelManagementService, "list_all_models", fake_list_all_models)

    with pytest.raises(HTTPException) as exc:
        await routes_models.activate_model(
            routes_models.ActivateModelRequest(model_name="risk_autoencoder", model_version="20260301099999"),
            claims,
        )

    assert exc.value.status_code == 404
    assert "inference-only" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_training_runs_normalize_null_json_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    claims = AuthClaims(sub="tester", tenant_id="tenant-alpha", scopes=["models:read"])
    session = SimpleNamespace()
    run_id = uuid4()

    async def fake_list_training_runs(session_arg, *, model_name, since, limit):
        return [
            {
                "run_id": run_id,
                "model_name": "risk_autoencoder",
                "model_version": None,
                "status": "running",
                "started_at": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
                "finished_at": None,
                "parameters": None,
                "metrics": None,
                "initiated_by": "tester",
            }
        ]

    monkeypatch.setattr(routes_models.ModelOpsRepository, "list_training_runs", fake_list_training_runs)

    rows = await routes_models.training_runs(None, None, 10, claims, session)
    assert len(rows) == 1
    assert rows[0].parameters == {}
    assert rows[0].metrics == {}
