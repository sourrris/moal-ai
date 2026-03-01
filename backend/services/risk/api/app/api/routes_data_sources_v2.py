from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.infrastructure.db import get_db_session
from app.infrastructure.operational_repository_v2 import DataSourceRepository
from risk_common.schemas_v2 import AuthClaims, DataSourceRunSummary, DataSourceStatus

router = APIRouter(prefix="/v2/data-sources", tags=["data-sources-v2"])


@router.get("/status", response_model=list[DataSourceStatus])
async def data_source_status(
    _: AuthClaims = Depends(require_scope("connectors:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[DataSourceStatus]:
    rows = await DataSourceRepository.list_status(session)
    return [DataSourceStatus(**row) for row in rows]


@router.get("/runs", response_model=list[DataSourceRunSummary])
async def data_source_runs(
    source_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthClaims = Depends(require_scope("connectors:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[DataSourceRunSummary]:
    rows = await DataSourceRepository.list_runs(session, source_name=source_name, limit=limit)
    return [DataSourceRunSummary(**row) for row in rows]
