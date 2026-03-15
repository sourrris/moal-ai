from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from risk_common.schemas import (
    ModelListItem,
    ModelMetadata,
    ModelMetricsResponse,
    ModelsListResponse,
    ModelTrainRequest,
    ModelTrainResponse,
)
from risk_common.schemas_v2 import AuthClaims, ModelTrainingRun
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.application.risk_event_service import ModelGatewayError, ModelManagementService
from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.monitoring_repository import ModelRepository
from app.infrastructure.operational_repository_v2 import ModelOpsRepository

router = APIRouter(prefix="/v1/models", tags=["models"])
settings = get_settings()


class ActivateModelRequest(BaseModel):
    model_name: str
    model_version: str


ACTIVATION_MIN_SAMPLES = settings.model_activation_min_samples
ACTIVATION_MIN_RELATIVE_IMPROVEMENT = settings.model_activation_min_relative_improvement
ACTIVATION_THRESHOLD_RATIO_MIN = settings.model_activation_threshold_ratio_min
ACTIVATION_THRESHOLD_RATIO_MAX = settings.model_activation_threshold_ratio_max


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


def _as_dict(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _activation_error_detail(code: str, message: str, **extra: object) -> dict:
    payload = {"code": code, "message": message}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def _activation_http_error(code: str, message: str, **extra: object) -> HTTPException:
    status_map = {
        "not_registry_model": 404,
        "artifact_missing": 409,
        "invalid_metadata": 422,
    }
    return HTTPException(status_code=status_map.get(code, 422), detail=_activation_error_detail(code, message, **extra))


def _training_sample_count(row: dict | None) -> int:
    if not row:
        return 0
    metrics = _as_dict(row.get("metrics"))
    parameters = _as_dict(row.get("parameters"))
    dataset_summary = _as_dict(parameters.get("dataset_summary"))
    return _as_int(
        metrics.get("sample_count"),
        _as_int(
            dataset_summary.get("effective_sample_count"),
            _as_int(
                dataset_summary.get("raw_sample_count"),
                _as_int(parameters.get("effective_sample_count"), 0),
            ),
        ),
    )


def _training_val_loss(row: dict | None) -> float | None:
    if not row:
        return None
    metrics = _as_dict(row.get("metrics"))
    return _as_float(metrics.get("val_loss"), _as_float(metrics.get("train_loss")))


def _validate_activation_policy(
    *,
    candidate_model: dict,
    candidate_run: dict | None,
    active_model: ModelMetadata | None,
    active_run: dict | None,
) -> None:
    sample_count = _training_sample_count(candidate_run)
    if sample_count < ACTIVATION_MIN_SAMPLES:
        raise _activation_http_error(
            "invalid_metadata",
            "Activation rejected: candidate model training dataset is below minimum sample gate",
            minimum_samples=ACTIVATION_MIN_SAMPLES,
            sample_count=sample_count,
        )

    candidate_threshold = _as_float(candidate_model.get("threshold"))
    if candidate_threshold is None or not math.isfinite(candidate_threshold) or candidate_threshold <= 0:
        raise _activation_http_error(
            "invalid_metadata",
            "Activation rejected: candidate threshold metadata is invalid",
            candidate_threshold=candidate_threshold,
        )

    if active_model is not None:
        active_threshold = _as_float(active_model.threshold)
        if active_threshold is None or not math.isfinite(active_threshold) or active_threshold <= 0:
            raise _activation_http_error(
                "invalid_metadata",
                "Activation rejected: active model threshold metadata is invalid",
                active_threshold=active_threshold,
            )

        threshold_ratio = candidate_threshold / active_threshold
        if threshold_ratio < ACTIVATION_THRESHOLD_RATIO_MIN or threshold_ratio > ACTIVATION_THRESHOLD_RATIO_MAX:
            raise _activation_http_error(
                "invalid_metadata",
                "Activation rejected: candidate threshold is outside allowed range versus active model",
                active_threshold=active_threshold,
                candidate_threshold=candidate_threshold,
                threshold_ratio=threshold_ratio,
                min_ratio=ACTIVATION_THRESHOLD_RATIO_MIN,
                max_ratio=ACTIVATION_THRESHOLD_RATIO_MAX,
            )

        if active_model.model_version != str(candidate_model.get("model_version") or ""):
            candidate_val_loss = _training_val_loss(candidate_run)
            active_val_loss = _training_val_loss(active_run)
            if candidate_val_loss is None or active_val_loss is None or active_val_loss <= 0:
                raise _activation_http_error(
                    "invalid_metadata",
                    "Activation rejected: missing comparable validation losses for relative-improvement gate",
                    candidate_val_loss=candidate_val_loss,
                    active_val_loss=active_val_loss,
                )

            relative_improvement = (active_val_loss - candidate_val_loss) / active_val_loss
            if relative_improvement < ACTIVATION_MIN_RELATIVE_IMPROVEMENT:
                raise _activation_http_error(
                    "invalid_metadata",
                    "Activation rejected: candidate model failed relative-improvement gate",
                    relative_improvement=relative_improvement,
                    required_minimum=ACTIVATION_MIN_RELATIVE_IMPROVEMENT,
                    candidate_val_loss=candidate_val_loss,
                    active_val_loss=active_val_loss,
                )


def _map_activation_gateway_error(exc: ModelGatewayError) -> HTTPException:
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or "")
        message = str(detail.get("message") or "Model activation failed")
        extra = {k: v for k, v in detail.items() if k not in {"code", "message"}}
        if code in {"not_registry_model", "artifact_missing", "invalid_metadata"}:
            return _activation_http_error(code, message, **extra)

    return HTTPException(status_code=502, detail=f"Unable to activate model: {exc}")


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
        "dataset_lineage": {
            "source_table": "risk_decisions" if training_source == "historical_events" else "request_payload",
            "source_column": "feature_vector" if training_source == "historical_events" else "features",
            "tenant_id": tenant_id,
            "lookback_hours": payload.lookback_hours,
            "collected_at": datetime.now(tz=UTC).isoformat(),
            "compatibility_mode": "historical_events->risk_decisions.feature_vector",
        },
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

    feature_dim_histogram: dict[str, int] = {}
    for vector in training_features:
        if not vector:
            continue
        dim = str(len(vector))
        feature_dim_histogram[dim] = feature_dim_histogram.get(dim, 0) + 1
    run_parameters["dataset_summary"] = {
        "raw_sample_count": len(training_features),
        "feature_dim_histogram": feature_dim_histogram,
        "lookback_window_start": (datetime.now(tz=UTC) - timedelta(hours=payload.lookback_hours)).isoformat(),
        "lookback_window_end": datetime.now(tz=UTC).isoformat(),
    }

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
    dataset_summary = _as_dict(run_parameters.get("dataset_summary"))
    dataset_summary["effective_sample_count"] = len(normalized_features)
    dataset_summary["effective_feature_dim"] = feature_dim
    dataset_summary["dropped_sample_count"] = max(len(training_features) - len(normalized_features), 0)
    run_parameters["dataset_summary"] = dataset_summary

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
        "dataset_lineage": run_parameters.get("dataset_lineage"),
        "dataset_summary": run_parameters.get("dataset_summary"),
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
    session: AsyncSession = Depends(get_db_session),
) -> ModelMetadata:
    try:
        registry_models = await ModelManagementService.list_all_models()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Unable to validate registry model artifacts for activation") from exc

    candidate_model = next(
        (
            model
            for model in registry_models
            if str(model.get("model_name") or "") == payload.model_name
            and str(model.get("model_version") or "") == payload.model_version
        ),
        None,
    )
    if not candidate_model:
        raise _activation_http_error(
            "not_registry_model",
            "Activation rejected: model is not present in the registry catalog",
            model_name=payload.model_name,
            model_version=payload.model_version,
        )

    candidate_run = await ModelOpsRepository.get_latest_successful_training_run(
        session,
        model_name=payload.model_name,
        model_version=payload.model_version,
    )
    if not candidate_run:
        raise _activation_http_error(
            "invalid_metadata",
            "Activation rejected: no successful training run metadata found for requested model version",
            model_name=payload.model_name,
            model_version=payload.model_version,
        )

    active_model: ModelMetadata | None = None
    active_run: dict | None = None
    try:
        active_payload = await ModelManagementService.get_active_model()
        active_model = _normalize_model_metadata(active_payload)
    except Exception:  # noqa: BLE001
        active_model = None

    if active_model:
        active_run = await ModelOpsRepository.get_latest_successful_training_run(
            session,
            model_name=active_model.model_name,
            model_version=active_model.model_version,
        )

    _validate_activation_policy(
        candidate_model=candidate_model,
        candidate_run=candidate_run,
        active_model=active_model,
        active_run=active_run,
    )

    try:
        result = await ModelManagementService.activate_model(payload.model_dump())
    except ModelGatewayError as exc:
        raise _map_activation_gateway_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Unable to activate model: {exc}") from exc

    model = _normalize_model_metadata(result)
    if not model:
        raise _activation_http_error(
            "invalid_metadata",
            "Model activation returned malformed metadata payload",
            model_name=payload.model_name,
            model_version=payload.model_version,
        )
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
