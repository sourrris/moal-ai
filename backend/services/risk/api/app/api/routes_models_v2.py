from datetime import datetime

from fastapi import APIRouter, Depends, Query
from moal_common.schemas import ModelTrainingRun
from moal_common.schemas_v2 import AuthClaims
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/models", tags=["models"])


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
