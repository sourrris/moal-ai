import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from moal_common.schemas import ModelTrainingRun
from moal_common.schemas_v2 import AuthClaims
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.config import get_settings
from app.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/models", tags=["models"])
logger = logging.getLogger(__name__)
settings = get_settings()


class TrainFromHistoryRequest(BaseModel):
    model_name: str = "behavior_autoencoder"
    lookback_hours: int = Field(default=24, ge=1, le=720)
    max_samples: int = Field(default=2048, ge=64, le=20000)
    epochs: int = Field(default=12, ge=1, le=500)
    batch_size: int = Field(default=32, ge=1, le=2048)
    threshold_quantile: float = Field(default=0.99, gt=0.5, le=0.9999)
    auto_activate: bool = True


@router.get("/training-runs", response_model=list[ModelTrainingRun])
async def training_runs(
    model_name: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthClaims = Depends(require_scope("models:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[ModelTrainingRun]:
    conditions = []
    params: dict = {"limit": limit}

    if model_name:
        conditions.append("model_name = :model_name")
        params["model_name"] = model_name
    if since:
        conditions.append("started_at >= :since")
        params["since"] = since

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT * FROM model_training_runs {where}
        ORDER BY started_at DESC LIMIT :limit
    """
    result = await session.execute(text(query), params)
    rows = result.mappings().all()
    return [ModelTrainingRun(**dict(row)) for row in rows]


@router.get("/active")
async def active_model(
    _: AuthClaims = Depends(require_scope("models:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await session.execute(
        text("""
            SELECT * FROM model_registry
            WHERE status = 'active'
            ORDER BY activated_at DESC NULLS LAST
            LIMIT 1
        """)
    )
    row = result.mappings().fetchone()
    if not row:
        return {"active_model": None}
    return {"active_model": dict(row)}


@router.get("/list")
async def list_ml_models(
    _: AuthClaims = Depends(require_scope("models:read")),
) -> list[dict]:
    """Proxy to ML service /v1/models."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ml_inference_url}/v1/models")
            if resp.status_code == 200:
                return resp.json()
    except Exception:  # noqa: BLE001
        logger.warning("ML service unavailable")
    raise HTTPException(status_code=503, detail="ML service unavailable")


@router.get("/active-ml")
async def active_ml_model(
    _: AuthClaims = Depends(require_scope("models:read")),
) -> dict:
    """Proxy to ML service /v1/models/active."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ml_inference_url}/v1/models/active")
            if resp.status_code == 200:
                return resp.json()
    except Exception:  # noqa: BLE001
        logger.warning("ML service unavailable")
    raise HTTPException(status_code=503, detail="ML service unavailable")


@router.post("/train")
async def train_from_history(
    payload: TrainFromHistoryRequest,
    claims: AuthClaims = Depends(require_scope("models:write")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Train a new model using feature vectors from historical events in the database.

    This endpoint:
    1. Fetches stored feature vectors from behavior_events within the lookback window
    2. Records a training run in model_training_runs
    3. Sends the features to the ML service for training
    4. Updates the training run with results
    """
    import httpx

    run_id = uuid4()
    cutoff = datetime.now(tz=UTC) - timedelta(hours=payload.lookback_hours)

    # Fetch feature vectors from DB
    result = await session.execute(
        text("""
            SELECT features FROM behavior_events
            WHERE occurred_at >= :cutoff
              AND array_length(features, 1) > 0
            ORDER BY occurred_at DESC
            LIMIT :max_samples
        """),
        {"cutoff": cutoff, "max_samples": payload.max_samples},
    )
    rows = result.all()

    if len(rows) < 32:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient training data: found {len(rows)} events (minimum 32 required). "
            f"Try increasing lookback_hours or ingesting more events.",
        )

    features = [list(row[0]) for row in rows]
    feature_dim = len(features[0]) if features else 0

    # Record training run
    params_json = {
        "lookback_hours": payload.lookback_hours,
        "max_samples": payload.max_samples,
        "epochs": payload.epochs,
        "batch_size": payload.batch_size,
        "threshold_quantile": payload.threshold_quantile,
        "auto_activate": payload.auto_activate,
        "sample_count": len(features),
        "feature_dim": feature_dim,
    }

    await session.execute(
        text("""
            INSERT INTO model_training_runs (
                run_id, model_name, status, parameters, initiated_by
            ) VALUES (
                :run_id, :model_name, 'running', CAST(:params AS jsonb), :initiated_by
            )
        """),
        {
            "run_id": str(run_id),
            "model_name": payload.model_name,
            "params": __import__("json").dumps(params_json),
            "initiated_by": claims.sub,
        },
    )
    await session.commit()

    # Send to ML service
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.ml_inference_url}/v1/models/train",
                json={
                    "model_name": payload.model_name,
                    "training_source": "provided_features",
                    "features": features,
                    "epochs": payload.epochs,
                    "batch_size": payload.batch_size,
                    "threshold_quantile": payload.threshold_quantile,
                    "auto_activate": payload.auto_activate,
                },
            )

        if resp.status_code != 200:
            # Mark training as failed
            await session.execute(
                text("""
                    UPDATE model_training_runs
                    SET status = 'failed', finished_at = NOW(),
                        notes = :notes
                    WHERE run_id = :run_id
                """),
                {"run_id": str(run_id), "notes": resp.text[:2000]},
            )
            await session.commit()
            raise HTTPException(status_code=resp.status_code, detail=f"ML training failed: {resp.text[:500]}")

        ml_result = resp.json()

        # Mark training as completed
        await session.execute(
            text("""
                UPDATE model_training_runs
                SET status = 'completed', finished_at = NOW(),
                    model_version = :model_version,
                    metrics = CAST(:metrics AS jsonb)
                WHERE run_id = :run_id
            """),
            {
                "run_id": str(run_id),
                "model_version": ml_result.get("model_version", ""),
                "metrics": __import__("json").dumps(ml_result.get("training_metrics", {})),
            },
        )
        await session.commit()

        return {
            "run_id": str(run_id),
            "status": "completed",
            **ml_result,
        }

    except httpx.HTTPError as exc:
        await session.execute(
            text("""
                UPDATE model_training_runs
                SET status = 'failed', finished_at = NOW(),
                    notes = :notes
                WHERE run_id = :run_id
            """),
            {"run_id": str(run_id), "notes": str(exc)[:2000]},
        )
        await session.commit()
        raise HTTPException(status_code=503, detail="ML service unavailable for training") from exc


@router.post("/activate")
async def activate_model(
    model_name: str,
    model_version: str,
    _: AuthClaims = Depends(require_scope("models:write")),
) -> dict:
    """Proxy activation request to ML service."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ml_inference_url}/v1/models/activate",
                json={"model_name": model_name, "model_version": model_version},
            )
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="ML service unavailable") from exc
