import logging
import json
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from moal_common.schemas import (
    BatchEventIngest,
    BatchIngestResult,
    BehaviorEventIngest,
    BehaviorEventResponse,
    EventIngestResult,
)
from moal_common.schemas_v2 import AuthClaims
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.application.feature_engineering import compute_features
from app.config import get_settings
from app.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/events", tags=["events"])
logger = logging.getLogger(__name__)
settings = get_settings()


async def _score_event(features: list[float]) -> dict | None:
    """Call the ML service for anomaly scoring. Returns None if ML is unavailable."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.ml_inference_url}/v1/infer",
                json={"event_id": "00000000-0000-0000-0000-000000000000", "features": features},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:  # noqa: BLE001
        logger.warning("ML service unavailable, skipping scoring")
    return None


async def _ingest_single(
    event: BehaviorEventIngest,
    session: AsyncSession,
) -> EventIngestResult:
    if event.occurred_at.tzinfo is None:
        event.occurred_at = event.occurred_at.replace(tzinfo=UTC)

    features = compute_features(event)
    hour_of_day = event.occurred_at.hour
    day_of_week = event.occurred_at.weekday()

    # Insert behavior event
    result = await session.execute(
        text("""
            INSERT INTO behavior_events (
                event_id, user_identifier, event_type, source, source_ip, user_agent,
                geo_country, geo_city, hour_of_day, day_of_week,
                session_duration_seconds, request_count, failed_auth_count,
                bytes_transferred, endpoint, status_code, device_fingerprint,
                metadata, features, occurred_at
            ) VALUES (
                :event_id, :user_identifier, :event_type, :source, :source_ip, :user_agent,
                :geo_country, :geo_city, :hour_of_day, :day_of_week,
                :session_duration_seconds, :request_count, :failed_auth_count,
                :bytes_transferred, :endpoint, :status_code, :device_fingerprint,
                CAST(:metadata AS jsonb), :features, :occurred_at
            )
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
        """),
        {
            "event_id": str(event.event_id),
            "user_identifier": event.user_identifier,
            "event_type": event.event_type,
            "source": event.source,
            "source_ip": event.source_ip,
            "user_agent": event.user_agent,
            "geo_country": event.geo_country,
            "geo_city": event.geo_city,
            "hour_of_day": hour_of_day,
            "day_of_week": day_of_week,
            "session_duration_seconds": event.session_duration_seconds,
            "request_count": event.request_count,
            "failed_auth_count": event.failed_auth_count,
            "bytes_transferred": event.bytes_transferred,
            "endpoint": event.endpoint,
            "status_code": event.status_code,
            "device_fingerprint": event.device_fingerprint,
            "metadata": json.dumps(event.metadata or {}),
            "features": features,
            "occurred_at": event.occurred_at,
        },
    )
    row = result.fetchone()
    if not row:
        return EventIngestResult(event_id=event.event_id, status="duplicate")

    # Score with ML service (inline, synchronous)
    ml_result = await _score_event(features)
    anomaly_score = None
    is_anomaly = None

    if ml_result:
        anomaly_score = ml_result.get("anomaly_score")
        is_anomaly = ml_result.get("is_anomaly", False)
        threshold = ml_result.get("threshold", 0.0)
        model_name = ml_result.get("model_name", "unknown")
        model_version = ml_result.get("model_version", "unknown")

        # Save anomaly result
        await session.execute(
            text("""
                INSERT INTO anomaly_results (
                    event_id, anomaly_score, threshold, is_anomaly,
                    model_name, model_version, feature_vector
                ) VALUES (
                    :event_id, :anomaly_score, :threshold, :is_anomaly,
                    :model_name, :model_version, :feature_vector
                )
            """),
            {
                "event_id": str(event.event_id),
                "anomaly_score": anomaly_score,
                "threshold": threshold,
                "is_anomaly": is_anomaly,
                "model_name": model_name,
                "model_version": model_version,
                "feature_vector": features,
            },
        )

        # Create alert if anomalous
        if is_anomaly:
            severity = "critical" if anomaly_score > threshold * 1.5 else "high"
            await session.execute(
                text("""
                    INSERT INTO alerts (
                        event_id, severity, anomaly_score, threshold,
                        model_name, model_version, state, user_identifier
                    ) VALUES (
                        :event_id, :severity, :anomaly_score, :threshold,
                        :model_name, :model_version, 'open', :user_identifier
                    )
                """),
                {
                    "event_id": str(event.event_id),
                    "severity": severity,
                    "anomaly_score": anomaly_score,
                    "threshold": threshold,
                    "model_name": model_name,
                    "model_version": model_version,
                    "user_identifier": event.user_identifier,
                },
            )

    await session.commit()
    return EventIngestResult(
        event_id=event.event_id,
        status="accepted",
        anomaly_score=anomaly_score,
        is_anomaly=is_anomaly,
    )


@router.post("/ingest", response_model=EventIngestResult, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    payload: BehaviorEventIngest,
    claims: AuthClaims = Depends(require_scope("events:write")),
    session: AsyncSession = Depends(get_db_session),
) -> EventIngestResult:
    try:
        return await _ingest_single(payload, session)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Unable to ingest event: {exc}") from exc


@router.post("/ingest/batch", response_model=BatchIngestResult, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event_batch(
    payload: BatchEventIngest,
    claims: AuthClaims = Depends(require_scope("events:write")),
    session: AsyncSession = Depends(get_db_session),
) -> BatchIngestResult:
    accepted = 0
    duplicates = 0
    failed = 0
    results: list[EventIngestResult] = []

    for item in payload.events:
        try:
            result = await _ingest_single(item, session)
            if result.status == "accepted":
                accepted += 1
            elif result.status == "duplicate":
                duplicates += 1
            else:
                failed += 1
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Batch ingestion failed for event {item.event_id}: {exc}")
            failed += 1
            results.append(EventIngestResult(event_id=item.event_id, status="failed"))

    return BatchIngestResult(accepted=accepted, duplicates=duplicates, failed=failed, results=results)


@router.get("", response_model=list[BehaviorEventResponse])
async def list_events(
    user_identifier: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    claims: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[BehaviorEventResponse]:
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if user_identifier:
        conditions.append("be.user_identifier = :user_identifier")
        params["user_identifier"] = user_identifier
    if event_type:
        conditions.append("be.event_type = :event_type")
        params["event_type"] = event_type

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT be.*, ar.anomaly_score, ar.is_anomaly
        FROM behavior_events be
        LEFT JOIN anomaly_results ar ON ar.event_id = be.event_id
        {where}
        ORDER BY be.occurred_at DESC
        LIMIT :limit OFFSET :offset
    """
    result = await session.execute(text(query), params)
    rows = result.mappings().all()
    return [
        BehaviorEventResponse(
            event_id=row["event_id"],
            user_identifier=row["user_identifier"],
            event_type=row["event_type"],
            source=row["source"],
            source_ip=str(row["source_ip"]) if row["source_ip"] else None,
            geo_country=row["geo_country"],
            geo_city=row["geo_city"],
            session_duration_seconds=row["session_duration_seconds"],
            request_count=row["request_count"],
            failed_auth_count=row["failed_auth_count"],
            endpoint=row["endpoint"],
            status_code=row["status_code"],
            device_fingerprint=row["device_fingerprint"],
            anomaly_score=row["anomaly_score"],
            is_anomaly=row["is_anomaly"],
            occurred_at=row["occurred_at"],
            ingested_at=row["ingested_at"],
        )
        for row in rows
    ]
