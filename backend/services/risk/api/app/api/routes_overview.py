from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_subject
from app.infrastructure.db import get_db_session
from app.infrastructure.monitoring_repository import MonitoringRepository

router = APIRouter(prefix="/v1/overview", tags=["overview"])

WINDOW_TO_HOURS = {"1h": 1, "24h": 24, "7d": 24 * 7}


@router.get("/metrics")
async def overview_metrics(
    tenant_id: str | None = Query(default=None),
    window: str = Query(default="24h"),
    _: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    hours = WINDOW_TO_HOURS.get(window, 24)
    from_ts = datetime.now(tz=UTC) - timedelta(hours=hours)
    return await MonitoringRepository.overview_metrics(
        session,
        tenant_id=tenant_id,
        from_ts=from_ts,
        window_hours=hours,
    )
