from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_subject, get_rabbit_channel
from app.application.services import EventIngestionService
from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.repositories import EventRepository
from risk_common.messaging import publish_json
from risk_common.schemas import EventEnvelope, EventIngestRequest

router = APIRouter(prefix="/v1/events", tags=["events"])
settings = get_settings()


@router.post("/ingest")
async def ingest_event(
    payload: EventIngestRequest,
    subject: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
    channel=Depends(get_rabbit_channel),
) -> dict:
    envelope = EventEnvelope(**payload.model_dump())
    created = await EventIngestionService.persist_event(session, envelope, submitted_by=subject)
    if not created:
        return {
            "status": "duplicate",
            "event_id": str(envelope.event_id),
            "message": "Event already exists and will not be re-queued.",
        }

    await publish_json(
        channel=channel,
        exchange_name=settings.rabbitmq_events_exchange,
        routing_key=settings.rabbitmq_events_routing_key,
        payload=envelope.model_dump(mode="json"),
        headers={"x-retry-count": 0},
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
    event = await EventRepository.fetch_by_id(session, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return {
        "event_id": str(event.event_id),
        "tenant_id": event.tenant_id,
        "event_type": event.event_type,
        "status": event.status,
        "ingested_at": event.ingested_at,
    }
