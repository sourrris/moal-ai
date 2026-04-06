from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from moal_common.schemas_v2 import AuthClaims
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_claims
from app.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/overview", tags=["overview"])

WINDOW_TO_HOURS = {"1h": 1, "24h": 24, "7d": 24 * 7}


@router.get("/metrics")
async def overview_metrics(
    window: str = Query(default="24h"),
    _: AuthClaims = Depends(get_auth_claims),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    hours = WINDOW_TO_HOURS.get(window, 24)
    from_ts = datetime.now(tz=UTC) - timedelta(hours=hours)

    events_result = await session.execute(
        text("SELECT COUNT(*) AS cnt FROM behavior_events WHERE occurred_at >= :from_ts"),
        {"from_ts": from_ts},
    )
    total_events = events_result.scalar() or 0

    alerts_result = await session.execute(
        text("SELECT COUNT(*) AS cnt FROM alerts WHERE created_at >= :from_ts"),
        {"from_ts": from_ts},
    )
    total_alerts = alerts_result.scalar() or 0

    open_alerts_result = await session.execute(
        text("SELECT COUNT(*) AS cnt FROM alerts WHERE state = 'open'"),
    )
    open_alerts = open_alerts_result.scalar() or 0

    anomaly_result = await session.execute(
        text("""
            SELECT COALESCE(AVG(anomaly_score), 0) AS avg_score
            FROM anomaly_results WHERE created_at >= :from_ts
        """),
        {"from_ts": from_ts},
    )
    avg_anomaly_score = float(anomaly_result.scalar() or 0)

    return {
        "window": window,
        "total_events": total_events,
        "total_alerts": total_alerts,
        "open_alerts": open_alerts,
        "avg_anomaly_score": round(avg_anomaly_score, 4),
    }
