from datetime import datetime

from fastapi import APIRouter, Depends, Query
from risk_common.schemas_v2 import AuthClaims, ModelDriftSnapshot, ModelTrainingRun
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.infrastructure.db import get_db_session
from app.infrastructure.operational_repository_v2 import ModelOpsRepository

router = APIRouter(prefix="/v2/models", tags=["models-v2"])


@router.get("/drift", response_model=list[ModelDriftSnapshot])
async def model_drift(
    model_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    claims: AuthClaims = Depends(require_scope("models:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[ModelDriftSnapshot]:
    rows = await ModelOpsRepository.list_drift_snapshots(
        session,
        tenant_id=claims.tenant_id,
        model_name=model_name,
        limit=limit,
    )
    return [ModelDriftSnapshot(**row) for row in rows]


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
    return [ModelTrainingRun(**row) for row in rows]
