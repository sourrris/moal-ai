from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from moal_common.schemas_v2 import AuthClaims
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_claims
from app.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/overview", tags=["overview"])

WINDOW_TO_HOURS = {"1h": 1, "24h": 24, "7d": 24 * 7}


def _normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_time_range(
    window: str | None,
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[str, datetime | None, datetime | None]:
    normalized_start = _normalize_dt(start_at)
    normalized_end = _normalize_dt(end_at)

    if normalized_start and normalized_end and normalized_start > normalized_end:
        normalized_start, normalized_end = normalized_end, normalized_start

    if normalized_start or normalized_end:
        return "custom", normalized_start, normalized_end

    normalized_window = (window or "all").lower()
    if normalized_window == "all":
        return "all", None, None
    if normalized_window in WINDOW_TO_HOURS:
        return normalized_window, datetime.now(tz=UTC) - timedelta(hours=WINDOW_TO_HOURS[normalized_window]), None
    return "all", None, None


def _build_time_clause(column: str, start_at: datetime | None, end_at: datetime | None) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict[str, datetime] = {}

    if start_at is not None:
        clauses.append(f"{column} >= :start_at")
        params["start_at"] = start_at
    if end_at is not None:
        clauses.append(f"{column} <= :end_at")
        params["end_at"] = end_at

    if not clauses:
        return "", params
    return f"WHERE {' AND '.join(clauses)}", params


async def _overview_metrics_payload(
    window: str,
    start_at: datetime | None,
    end_at: datetime | None,
    session: AsyncSession,
) -> dict:
    normalized_window, normalized_start, normalized_end = _resolve_time_range(window, start_at, end_at)
    events_where, params = _build_time_clause("occurred_at", normalized_start, normalized_end)
    alerts_where, _ = _build_time_clause("created_at", normalized_start, normalized_end)

    events_result = await session.execute(
        text(f"SELECT COUNT(*) AS cnt FROM behavior_events {events_where}"),
        params,
    )
    total_events = events_result.scalar() or 0

    alerts_result = await session.execute(
        text(f"SELECT COUNT(*) AS cnt FROM alerts {alerts_where}"),
        params,
    )
    total_alerts = alerts_result.scalar() or 0

    open_alerts_result = await session.execute(
        text("SELECT COUNT(*) AS cnt FROM alerts WHERE state = 'open'"),
    )
    open_alerts = open_alerts_result.scalar() or 0

    anomaly_result = await session.execute(
        text(f"""
            SELECT COALESCE(AVG(anomaly_score), 0) AS avg_score
            FROM anomaly_results {alerts_where}
        """),
        params,
    )
    avg_anomaly_score = float(anomaly_result.scalar() or 0)

    return {
        "window": normalized_window,
        "total_events": total_events,
        "total_alerts": total_alerts,
        "open_alerts": open_alerts,
        "avg_anomaly_score": round(avg_anomaly_score, 4),
    }


@router.get("")
async def overview_metrics_alias(
    window: str = Query(default="all"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    _: AuthClaims = Depends(get_auth_claims),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _overview_metrics_payload(window, start_at, end_at, session)


@router.get("/metrics")
async def overview_metrics(
    window: str = Query(default="all"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    _: AuthClaims = Depends(get_auth_claims),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _overview_metrics_payload(window, start_at, end_at, session)
