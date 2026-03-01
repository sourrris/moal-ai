from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.application.services import ModelManagementService
from app.infrastructure.db import get_db_session
from app.infrastructure.repositories import ModelRepository
from app.infrastructure.repositories_v2 import ModelOpsRepository
from risk_common.schemas import (
    ModelListItem,
    ModelMetadata,
    ModelMetricsResponse,
    ModelTrainRequest,
    ModelTrainResponse,
    ModelsListResponse,
)
from risk_common.schemas_v2 import AuthClaims, ModelTrainingRun

router = APIRouter(prefix="/v1/models", tags=["models"])


class ActivateModelRequest(BaseModel):
    model_name: str
    model_version: str


def _as_float(value: object | None, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return float(stripped)
        except ValueError:
            return default
    return default


def _as_int(value: object | None, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(float(stripped))
        except ValueError:
            return default
    return default


def _normalize_model_metadata(payload: dict | None) -> ModelMetadata | None:
    if not payload:
        return None
    try:
        return ModelMetadata.model_validate(payload)
    except Exception:  # noqa: BLE001
        return None


def _normalize_model_item(raw: dict, *, active_name: str | None, active_version: str | None) -> ModelListItem:
    model_name = str(raw.get("model_name") or "")
    model_version = str(raw.get("model_version") or "")
    source = str(raw.get("source") or "registry")
    if source not in {"registry", "inference_only"}:
        source = "registry"

    return ModelListItem(
        model_name=model_name,
        model_version=model_version,
        threshold=_as_float(raw.get("threshold"), None),
        updated_at=raw.get("updated_at"),
        inference_count=_as_int(raw.get("inference_count"), 0),
        anomaly_rate=_as_float(raw.get("anomaly_rate"), 0.0) or 0.0,
        active=(model_name == active_name and model_version == active_version),
        activate_capable=bool(raw.get("activate_capable", source == "registry")),
        source=source,  # type: ignore[arg-type]
    )


def _normalize_training_features(
    features: list[list[float]],
    *,
    min_samples: int,
    max_samples: int,
) -> tuple[list[list[float]], int]:
    if not features:
        raise ValueError("No training features available")

    feature_dims: dict[int, int] = {}
    for vector in features:
        if not vector:
            continue
        feature_dims[len(vector)] = feature_dims.get(len(vector), 0) + 1
    if not feature_dims:
        raise ValueError("Training features are empty")

    dominant_dim = max(feature_dims, key=feature_dims.get)
    normalized = [[float(v) for v in vector] for vector in features if len(vector) == dominant_dim]
    if len(normalized) > max_samples:
        normalized = normalized[:max_samples]

    if len(normalized) < min_samples:
        raise ValueError(
            f"Need at least {min_samples} samples with feature_dim={dominant_dim}; only {len(normalized)} available"
        )

    return normalized, dominant_dim


@router.get("/active", response_model=ModelMetadata)
async def get_active_model(_: AuthClaims = Depends(require_scope("models:read"))) -> ModelMetadata:
    payload = await ModelManagementService.get_active_model()
    model = _normalize_model_metadata(payload)
    if not model:
        raise HTTPException(status_code=503, detail="Active model metadata unavailable")
    return model


@router.post("/train", response_model=ModelTrainResponse)
async def train_model(
    payload: ModelTrainRequest,
    claims: AuthClaims = Depends(require_scope("models:write")),
    session: AsyncSession = Depends(get_db_session),
) -> ModelTrainResponse:
    tenant_id = payload.tenant_id or claims.tenant_id
    training_source = payload.training_source

    run_parameters: dict[str, object] = {
        "training_source": training_source,
        "tenant_id": tenant_id,
        "lookback_hours": payload.lookback_hours,
        "max_samples": payload.max_samples,
        "min_samples": payload.min_samples,
        "epochs": payload.epochs,
        "batch_size": payload.batch_size,
        "threshold_quantile": payload.threshold_quantile,
        "auto_activate": payload.auto_activate,
    }

    run_id = await ModelOpsRepository.create_training_run(
        session,
        model_name=payload.model_name,
        parameters=run_parameters,
        initiated_by=claims.sub,
    )

    training_features = payload.features or []
    if training_source == "historical_events":
        training_features = await ModelRepository.fetch_training_features(
            session,
            tenant_id=tenant_id,
            lookback_hours=payload.lookback_hours,
            max_samples=payload.max_samples,
        )

    try:
        normalized_features, feature_dim = _normalize_training_features(
            training_features,
            min_samples=payload.min_samples,
            max_samples=payload.max_samples,
        )
    except ValueError as exc:
        await ModelOpsRepository.finalize_training_run(
            session,
            run_id=run_id,
            status="failed",
            model_version=None,
            metrics={"error": str(exc), "parameters": run_parameters},
            parameters=run_parameters,
            notes=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_parameters["requested_sample_count"] = len(training_features)
    run_parameters["effective_sample_count"] = len(normalized_features)
    run_parameters["feature_dim"] = feature_dim

    active_before: dict | None = None
    try:
        active_before = await ModelManagementService.get_active_model()
    except Exception:  # noqa: BLE001
        active_before = None

    ml_payload = {
        "model_name": payload.model_name,
        "training_source": "provided_features",
        "tenant_id": tenant_id,
        "features": normalized_features,
        "epochs": payload.epochs,
        "batch_size": payload.batch_size,
        "threshold_quantile": payload.threshold_quantile,
        "auto_activate": payload.auto_activate,
    }

    try:
        result = await ModelManagementService.train_model(ml_payload)
    except Exception as exc:  # noqa: BLE001
        await ModelOpsRepository.finalize_training_run(
            session,
            run_id=run_id,
            status="failed",
            model_version=None,
            metrics={"error": str(exc), "parameters": run_parameters},
            parameters=run_parameters,
            notes=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"Model training failed: {exc}") from exc

    train_metrics = result.get("training_metrics") if isinstance(result.get("training_metrics"), dict) else {}
    active_threshold = _as_float(active_before.get("threshold")) if active_before else None
    candidate_threshold = _as_float(result.get("threshold"))
    baseline_comparison = {
        "active_model_version": active_before.get("model_version") if active_before else None,
        "active_threshold": active_threshold,
        "candidate_threshold": candidate_threshold,
        "threshold_delta": (
            (candidate_threshold - active_threshold)
            if active_threshold is not None and candidate_threshold is not None
            else None
        ),
        "threshold_ratio": (
            (candidate_threshold / active_threshold)
            if active_threshold not in {None, 0.0} and candidate_threshold is not None
            else None
        ),
    }
    combined_metrics = {
        **train_metrics,
        "sample_count": len(normalized_features),
        "feature_dim": feature_dim,
        "training_source": training_source,
        "baseline_comparison": baseline_comparison,
    }

    await ModelOpsRepository.finalize_training_run(
        session,
        run_id=run_id,
        status="success",
        model_version=str(result.get("model_version") or ""),
        metrics=combined_metrics,
        parameters=run_parameters,
    )

    return ModelTrainResponse(
        run_id=run_id,
        status="success",
        model_name=str(result.get("model_name") or payload.model_name),
        model_version=str(result.get("model_version") or ""),
        feature_dim=_as_int(result.get("feature_dim"), feature_dim),
        threshold=_as_float(result.get("threshold")),
        updated_at=result.get("updated_at"),
        training_source=training_source,
        sample_count=_as_int(result.get("sample_count"), len(normalized_features)),
        auto_activated=bool(result.get("auto_activated", False)),
        metrics=combined_metrics,
    )


@router.post("/activate", response_model=ModelMetadata)
async def activate_model(
    payload: ActivateModelRequest,
    _: AuthClaims = Depends(require_scope("models:write")),
) -> ModelMetadata:
    try:
        registry_models = await ModelManagementService.list_all_models()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Unable to validate registry model artifacts for activation") from exc

    is_registry_model = any(
        str(model.get("model_name") or "") == payload.model_name
        and str(model.get("model_version") or "") == payload.model_version
        for model in registry_models
    )
    if not is_registry_model:
        raise HTTPException(
            status_code=404,
            detail="Activation rejected: model is inference-only or registry artifacts are missing",
        )

    try:
        result = await ModelManagementService.activate_model(payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Unable to activate model: {exc}") from exc

    model = _normalize_model_metadata(result)
    if not model:
        raise HTTPException(status_code=500, detail="Model activation returned invalid metadata")
    return model


@router.get("", response_model=ModelsListResponse)
async def list_models(
    _: AuthClaims = Depends(require_scope("models:read")),
    session: AsyncSession = Depends(get_db_session),
) -> ModelsListResponse:
    try:
        active_payload = await ModelManagementService.get_active_model()
    except Exception:  # noqa: BLE001
        active_payload = None
    active_model = _normalize_model_metadata(active_payload)
    active_version = active_model.model_version if active_model else None
    active_name = active_model.model_name if active_model else None

    try:
        ml_models = await ModelManagementService.list_all_models()
    except Exception:  # noqa: BLE001
        ml_models = []

    stats_list = await ModelRepository.list_models(session)
    stats_map = {(str(s["model_name"]), str(s["model_version"])): s for s in stats_list}

    merged: list[ModelListItem] = []
    for model in ml_models:
        key = (str(model.get("model_name") or ""), str(model.get("model_version") or ""))
        stats = stats_map.get(key, {})
        merged.append(
            _normalize_model_item(
                {
                    "model_name": key[0],
                    "model_version": key[1],
                    "threshold": stats.get("threshold", model.get("threshold")),
                    "updated_at": stats.get("updated_at", model.get("updated_at")),
                    "inference_count": stats.get("inference_count", 0),
                    "anomaly_rate": stats.get("anomaly_rate", 0),
                    "activate_capable": True,
                    "source": "registry",
                },
                active_name=active_name,
                active_version=active_version,
            )
        )

    existing_keys = {(item.model_name, item.model_version) for item in merged}
    for stats in stats_list:
        key = (str(stats.get("model_name") or ""), str(stats.get("model_version") or ""))
        if key in existing_keys:
            continue
        merged.append(
            _normalize_model_item(
                {
                    **stats,
                    "activate_capable": False,
                    "source": "inference_only",
                },
                active_name=active_name,
                active_version=active_version,
            )
        )

    merged.sort(
        key=lambda item: item.updated_at.timestamp() if item.updated_at is not None else 0.0,
        reverse=True,
    )
    return ModelsListResponse(active_model=active_model, items=merged)


@router.get("/training-runs", response_model=list[ModelTrainingRun])
async def training_runs(
    model_name: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthClaims = Depends(require_scope("models:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[ModelTrainingRun]:
    rows = await ModelOpsRepository.list_training_runs(
        session,
        model_name=model_name,
        since=since,
        limit=limit,
    )
    normalized_rows: list[ModelTrainingRun] = []
    for row in rows:
        payload = dict(row)
        payload["parameters"] = payload.get("parameters") or {}
        payload["metrics"] = payload.get("metrics") or {}
        normalized_rows.append(ModelTrainingRun(**payload))
    return normalized_rows


@router.get("/{model_version}/metrics", response_model=ModelMetricsResponse)
async def model_metrics(
    model_version: str,
    _: AuthClaims = Depends(require_scope("models:read")),
    session: AsyncSession = Depends(get_db_session),
) -> ModelMetricsResponse:
    payload = await ModelRepository.model_metrics(session, model_version)
    return ModelMetricsResponse.model_validate(payload)
