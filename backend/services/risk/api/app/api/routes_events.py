from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from risk_common.messaging import publish_json_with_compat
from risk_common.schemas import EventEnvelope, EventIngestRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_subject, get_rabbit_channel
from app.application.risk_event_service import EventIngestionService
from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.monitoring_repository import EventRepository

router = APIRouter(prefix="/v1/events", tags=["events"])
settings = get_settings()


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    payload: EventIngestRequest,
    subject: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
    channel=Depends(get_rabbit_channel),
) -> dict:
    envelope = EventEnvelope(**payload.model_dump())
    created = await EventIngestionService.persist_event(session, envelope, submitted_by=subject)
    if not created:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "duplicate",
                "event_id": str(envelope.event_id),
                "message": "Event already exists and will not be re-queued.",
            },
        )

    await publish_json_with_compat(
        channel=channel,
        exchange_name=settings.rabbitmq_events_exchange,
        routing_key=settings.rabbitmq_events_routing_key,
        payload=envelope.model_dump(mode="json"),
        headers={"x-retry-count": 0},
        legacy_exchange_name=settings.rabbitmq_events_exchange_legacy,
        legacy_routing_key=settings.rabbitmq_events_routing_key_legacy,
    )

    return {
        "status": "accepted",
        "event_id": str(envelope.event_id),
        "queued": True,
    }


@router.get("/{event_id}")
async def get_event_status(
    event_id: UUID,
    _: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    event = await EventRepository.fetch_event_detail(session, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


@router.get("")
async def list_events(
    tenant_id: str | None = Query(default=None),
    domain_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    source: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    page: int | None = Query(default=None, ge=1),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    _: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await EventRepository.list_events(
        session,
        tenant_id=tenant_id,
        domain_id=domain_id,
        status=status,
        severity=severity,
        source=source,
        event_type=event_type,
        from_ts=start_date or from_ts,
        to_ts=end_date or to_ts,
        page=page,
        cursor=cursor,
        limit=limit,
    )
