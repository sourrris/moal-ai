from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from moal_common.schemas_v2 import AuthClaims
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

WINDOW_TO_HOURS = {"1h": 1, "24h": 24, "7d": 24 * 7, "30d": 24 * 30}


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


async def _fetch_events_by_type(
    session: AsyncSession,
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[dict]:
    where, params = _build_time_clause("occurred_at", start_at, end_at)
    result = await session.execute(
        text("""
            SELECT event_type, COUNT(*) AS count
            FROM behavior_events
            {where}
            GROUP BY event_type
            ORDER BY count DESC, event_type ASC
        """.format(where=where)),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


async def _fetch_events_by_hour(
    session: AsyncSession,
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[dict]:
    where, params = _build_time_clause("occurred_at", start_at, end_at)
    result = await session.execute(
        text("""
            WITH hourly_counts AS (
                SELECT COALESCE(hour_of_day, EXTRACT(HOUR FROM occurred_at)::INT) AS hour,
                       COUNT(*) AS count
                FROM behavior_events
                {where}
                GROUP BY 1
            )
            SELECT gs.hour,
                   COALESCE(hc.count, 0) AS count
            FROM generate_series(0, 23) AS gs(hour)
            LEFT JOIN hourly_counts hc ON hc.hour = gs.hour
            ORDER BY gs.hour ASC
        """.format(where=where)),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


async def _fetch_top_users(
    session: AsyncSession,
    start_at: datetime | None,
    end_at: datetime | None,
    limit: int,
) -> list[dict]:
    where, params = _build_time_clause("be.occurred_at", start_at, end_at)
    params["limit"] = limit
    result = await session.execute(
        text("""
            SELECT be.user_identifier,
                   COUNT(*) AS event_count,
                   COALESCE(SUM(CASE WHEN ar.is_anomaly THEN 1 ELSE 0 END), 0) AS anomaly_count,
                   MAX(be.occurred_at) AS last_seen_at
            FROM behavior_events be
            LEFT JOIN anomaly_results ar ON ar.event_id = be.event_id
            {where}
            GROUP BY be.user_identifier
            ORDER BY event_count DESC, last_seen_at DESC
            LIMIT :limit
        """.format(where=where)),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


async def _fetch_geo_distribution(
    session: AsyncSession,
    start_at: datetime | None,
    end_at: datetime | None,
    limit: int,
) -> list[dict]:
    where, params = _build_time_clause("occurred_at", start_at, end_at)
    params["limit"] = limit
    result = await session.execute(
        text("""
            SELECT COALESCE(NULLIF(geo_country, ''), 'unknown') AS geo_country,
                   COUNT(*) AS count
            FROM behavior_events
            {where}
            GROUP BY 1
            ORDER BY count DESC, geo_country ASC
            LIMIT :limit
        """.format(where=where)),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/stats")
async def dashboard_stats(
    window: str = Query(default="all"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    _: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    normalized_window, normalized_start, normalized_end = _resolve_time_range(window, start_at, end_at)
    event_where, time_params = _build_time_clause("occurred_at", normalized_start, normalized_end)
    alerts_where, _ = _build_time_clause("created_at", normalized_start, normalized_end)
    auth_where = (
        f"{event_where} AND event_type = 'auth'"
        if event_where
        else "WHERE event_type = 'auth'"
    )

    totals_result = await session.execute(
        text("""
            SELECT
                (SELECT COUNT(*) FROM behavior_events {event_where}) AS total_events,
                (SELECT COUNT(*) FROM alerts {alerts_where}) AS total_alerts,
                (SELECT COUNT(*) FROM alerts WHERE state = 'open') AS open_alerts,
                (SELECT AVG(anomaly_score) FROM anomaly_results {alerts_where}) AS avg_anomaly_score,
                (
                    SELECT
                        COALESCE(
                            SUM(failed_auth_count)::DOUBLE PRECISION
                            / NULLIF(SUM(GREATEST(request_count, 1)), 0),
                            0.0
                        )
                    FROM behavior_events
                    {auth_where}
                ) AS auth_failure_rate
        """.format(
            event_where=event_where,
            alerts_where=alerts_where,
            auth_where=auth_where,
        )),
        time_params,
    )
    totals = totals_result.mappings().one()
    avg_anomaly_score = totals["avg_anomaly_score"]

    return {
        "window": normalized_window,
        "range_start": normalized_start,
        "range_end": normalized_end,
        "generated_at": datetime.now(tz=UTC),
        "total_events": totals["total_events"] or 0,
        "total_alerts": totals["total_alerts"] or 0,
        "open_alerts": totals["open_alerts"] or 0,
        "avg_anomaly_score": round(float(avg_anomaly_score), 4) if avg_anomaly_score is not None else None,
        "auth_failure_rate": round(float(totals["auth_failure_rate"] or 0.0), 4),
        "events_by_type": await _fetch_events_by_type(session, normalized_start, normalized_end),
        "events_by_hour": await _fetch_events_by_hour(session, normalized_start, normalized_end),
        "top_users": await _fetch_top_users(session, normalized_start, normalized_end, 10),
        "geo_distribution": await _fetch_geo_distribution(session, normalized_start, normalized_end, 8),
    }


@router.get("/events/recent")
async def dashboard_recent_events(
    window: str = Query(default="all"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _, normalized_start, normalized_end = _resolve_time_range(window, start_at, end_at)
    where, params = _build_time_clause("be.occurred_at", normalized_start, normalized_end)
    params["limit"] = limit
    params["offset"] = offset
    result = await session.execute(
        text("""
            SELECT be.event_id,
                   be.occurred_at,
                   be.user_identifier,
                   be.event_type,
                   be.source,
                   be.source_ip,
                   be.geo_country,
                   be.status_code,
                   be.failed_auth_count,
                   ar.anomaly_score,
                   ar.is_anomaly
            FROM behavior_events be
            LEFT JOIN anomaly_results ar ON ar.event_id = be.event_id
            {where}
            ORDER BY be.occurred_at DESC
            LIMIT :limit OFFSET :offset
        """.format(where=where)),
        params,
    )
    items = []
    for row in result.mappings().all():
        item = dict(row)
        if item.get("source_ip") is not None:
            item["source_ip"] = str(item["source_ip"])
        items.append(item)
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
    }


@router.get("/events/by-type")
async def dashboard_events_by_type(
    window: str = Query(default="all"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    _: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    _, normalized_start, normalized_end = _resolve_time_range(window, start_at, end_at)
    return await _fetch_events_by_type(session, normalized_start, normalized_end)


@router.get("/events/by-hour")
async def dashboard_events_by_hour(
    window: str = Query(default="all"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    _: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    _, normalized_start, normalized_end = _resolve_time_range(window, start_at, end_at)
    return await _fetch_events_by_hour(session, normalized_start, normalized_end)


@router.get("/users/top")
async def dashboard_top_users(
    window: str = Query(default="all"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    _: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    _, normalized_start, normalized_end = _resolve_time_range(window, start_at, end_at)
    return await _fetch_top_users(session, normalized_start, normalized_end, limit)


@router.get("/users/{user_identifier}/profile")
async def dashboard_user_profile(
    user_identifier: str,
    _: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return a rich profile for a single user: summary stats, event timeline, and anomaly scores."""
    # Summary stats
    stats_result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_events,
                COALESCE(SUM(CASE WHEN ar.is_anomaly THEN 1 ELSE 0 END), 0) AS total_anomalies,
                MIN(be.occurred_at) AS first_seen,
                MAX(be.occurred_at) AS last_seen,
                AVG(ar.anomaly_score) AS avg_anomaly_score,
                MAX(ar.anomaly_score) AS max_anomaly_score,
                COUNT(DISTINCT be.source_ip) AS unique_ips,
                COUNT(DISTINCT be.device_fingerprint) AS unique_devices,
                COUNT(DISTINCT be.geo_country) AS unique_countries
            FROM behavior_events be
            LEFT JOIN anomaly_results ar ON ar.event_id = be.event_id
            WHERE be.user_identifier = :uid
        """),
        {"uid": user_identifier},
    )
    stats = stats_result.mappings().one()

    # Event type breakdown
    types_result = await session.execute(
        text("""
            SELECT event_type, COUNT(*) AS count
            FROM behavior_events
            WHERE user_identifier = :uid
            GROUP BY event_type
            ORDER BY count DESC
        """),
        {"uid": user_identifier},
    )
    event_types = [dict(row) for row in types_result.mappings().all()]

    # Hourly pattern
    hours_result = await session.execute(
        text("""
            WITH hourly AS (
                SELECT COALESCE(hour_of_day, EXTRACT(HOUR FROM occurred_at)::INT) AS hour,
                       COUNT(*) AS count
                FROM behavior_events
                WHERE user_identifier = :uid
                GROUP BY 1
            )
            SELECT gs.hour, COALESCE(h.count, 0) AS count
            FROM generate_series(0, 23) AS gs(hour)
            LEFT JOIN hourly h ON h.hour = gs.hour
            ORDER BY gs.hour
        """),
        {"uid": user_identifier},
    )
    hourly_pattern = [dict(row) for row in hours_result.mappings().all()]

    # Recent events with anomaly scores (last 100)
    events_result = await session.execute(
        text("""
            SELECT be.event_id, be.occurred_at, be.event_type, be.source,
                   be.source_ip, be.geo_country, be.status_code,
                   be.failed_auth_count, be.device_fingerprint,
                   ar.anomaly_score, ar.is_anomaly, ar.threshold
            FROM behavior_events be
            LEFT JOIN anomaly_results ar ON ar.event_id = be.event_id
            WHERE be.user_identifier = :uid
            ORDER BY be.occurred_at DESC
            LIMIT 100
        """),
        {"uid": user_identifier},
    )
    events = []
    for row in events_result.mappings().all():
        item = dict(row)
        if item.get("source_ip") is not None:
            item["source_ip"] = str(item["source_ip"])
        events.append(item)

    # Source IPs used
    ips_result = await session.execute(
        text("""
            SELECT source_ip::TEXT AS ip, COUNT(*) AS count
            FROM behavior_events
            WHERE user_identifier = :uid AND source_ip IS NOT NULL
            GROUP BY source_ip
            ORDER BY count DESC
            LIMIT 10
        """),
        {"uid": user_identifier},
    )
    source_ips = [dict(row) for row in ips_result.mappings().all()]

    # Countries used
    geo_result = await session.execute(
        text("""
            SELECT COALESCE(NULLIF(geo_country, ''), 'unknown') AS country, COUNT(*) AS count
            FROM behavior_events
            WHERE user_identifier = :uid
            GROUP BY 1
            ORDER BY count DESC
        """),
        {"uid": user_identifier},
    )
    countries = [dict(row) for row in geo_result.mappings().all()]

    return {
        "user_identifier": user_identifier,
        "total_events": stats["total_events"] or 0,
        "total_anomalies": stats["total_anomalies"] or 0,
        "first_seen": stats["first_seen"],
        "last_seen": stats["last_seen"],
        "avg_anomaly_score": round(float(stats["avg_anomaly_score"]), 4) if stats["avg_anomaly_score"] is not None else None,
        "max_anomaly_score": round(float(stats["max_anomaly_score"]), 4) if stats["max_anomaly_score"] is not None else None,
        "unique_ips": stats["unique_ips"] or 0,
        "unique_devices": stats["unique_devices"] or 0,
        "unique_countries": stats["unique_countries"] or 0,
        "event_types": event_types,
        "hourly_pattern": hourly_pattern,
        "recent_events": events,
        "source_ips": source_ips,
        "countries": countries,
    }
