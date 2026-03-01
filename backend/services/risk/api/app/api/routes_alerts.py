from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_subject
from app.infrastructure.db import get_db_session
from app.infrastructure.monitoring_repository import MonitoringRepository

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    tenant_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    model_version: str | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    score_min: float | None = Query(default=None),
    score_max: float | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    _: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await MonitoringRepository.list_alerts(
        session,
        tenant_id=tenant_id,
        severity=severity,
        model_version=model_version,
        from_ts=from_ts,
        to_ts=to_ts,
        score_min=score_min,
        score_max=score_max,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{alert_id}")
async def alert_detail(
    alert_id: str,
    _: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    item = await MonitoringRepository.fetch_alert_detail(session, alert_id)
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found")
    return item
