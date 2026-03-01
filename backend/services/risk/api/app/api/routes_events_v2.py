import logging
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_rabbit_channel, require_scope
from app.application.risk_event_service import EventIngestionService
from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.operational_repository_v2 import EventV2Repository
from risk_common.messaging import publish_json_with_compat
from risk_common.schemas import EventEnvelope
from risk_common.schemas_v2 import (
    AuthClaims,
    BatchIngestResult,
    EventIngestResult,
    RiskEventBatchIngestRequest,
    RiskEventIngestRequest,
    RiskEventV2,
)

router = APIRouter(prefix="/v2/events", tags=["events-v2"])
logger = logging.getLogger(__name__)
settings = get_settings()


def _legacy_features(payload: RiskEventIngestRequest) -> list[float]:
    if payload.features and len(payload.features) >= 8:
        return payload.features[:8]

    tx = payload.transaction
    amount_norm = min(tx.amount / 10000.0, 1.0)
    is_cross_border = 1.0 if tx.source_country and tx.destination_country and tx.source_country != tx.destination_country else 0.0
    has_ip = 1.0 if tx.source_ip else 0.0
    has_bin = 1.0 if tx.card_bin else 0.0
    has_email_hash = 1.0 if tx.user_email_hash else 0.0
    metadata_size = min(len(tx.metadata) / 10.0, 1.0)
    merchant_hash = (hash(tx.merchant_id or "") % 1000) / 1000.0
    event_hash = (hash(payload.event_type) % 1000) / 1000.0
    return [amount_norm, is_cross_border, has_ip, has_bin, has_email_hash, metadata_size, merchant_hash, event_hash]


async def _ingest_single_event(
    payload: RiskEventIngestRequest,
    claims: AuthClaims,
    session: AsyncSession,
    channel,
) -> EventIngestResult:
    if payload.occurred_at.tzinfo is None:
        payload.occurred_at = payload.occurred_at.replace(tzinfo=timezone.utc)

    event = RiskEventV2(
        event_id=payload.event_id,
        idempotency_key=payload.idempotency_key,
        tenant_id=claims.tenant_id,
        source=payload.source,
        event_type=payload.event_type,
        transaction=payload.transaction,
        occurred_at=payload.occurred_at,
        submitted_by=claims.sub,
        features=payload.features,
    )

    created = await EventV2Repository.create_if_absent(session, event)
    if not created:
        return EventIngestResult(event_id=event.event_id, status="duplicate", queued=False)

    legacy_envelope = EventEnvelope(
        event_id=event.event_id,
        tenant_id=event.tenant_id,
        source=event.source,
        event_type=event.event_type,
        payload=event.transaction.model_dump(mode="json"),
        features=_legacy_features(payload),
        occurred_at=event.occurred_at,
        ingested_at=event.ingested_at,
    )
    await EventIngestionService.persist_event(session, legacy_envelope, submitted_by=claims.sub)

    await publish_json_with_compat(
        channel=channel,
        exchange_name=settings.rabbitmq_events_exchange,
        routing_key=settings.rabbitmq_events_routing_key,
        payload=legacy_envelope.model_dump(mode="json"),
        headers={"x-retry-count": 0, "x-schema-version": 1},
        legacy_exchange_name=settings.rabbitmq_events_exchange_legacy,
        legacy_routing_key=settings.rabbitmq_events_routing_key_legacy,
    )

    await publish_json_with_compat(
        channel=channel,
        exchange_name=settings.rabbitmq_events_exchange,
        routing_key=settings.rabbitmq_events_v2_routing_key,
        payload=event.model_dump(mode="json"),
        headers={"x-retry-count": 0, "x-schema-version": 2},
        legacy_exchange_name=settings.rabbitmq_events_exchange_legacy,
        legacy_routing_key=settings.rabbitmq_events_v2_routing_key_legacy,
    )

    return EventIngestResult(event_id=event.event_id, status="accepted", queued=True)


@router.post("/ingest", response_model=EventIngestResult)
async def ingest_event_v2(
    payload: RiskEventIngestRequest,
    claims: AuthClaims = Depends(require_scope("events:write")),
    session: AsyncSession = Depends(get_db_session),
    channel=Depends(get_rabbit_channel),
) -> EventIngestResult:
    try:
        return await _ingest_single_event(payload, claims, session, channel)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Unable to ingest event: {exc}") from exc


@router.post("/ingest/batch", response_model=BatchIngestResult)
async def ingest_event_batch_v2(
    payload: RiskEventBatchIngestRequest,
    claims: AuthClaims = Depends(require_scope("events:write")),
    session: AsyncSession = Depends(get_db_session),
    channel=Depends(get_rabbit_channel),
) -> BatchIngestResult:
    accepted = 0
    duplicates = 0
    failed = 0
    results: list[EventIngestResult] = []

    for item in payload.events:
        if item.occurred_at.tzinfo is None:
            item.occurred_at = item.occurred_at.replace(tzinfo=timezone.utc)
        try:
            result = await _ingest_single_event(item, claims, session, channel)
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
            results.append(EventIngestResult(event_id=item.event_id, status="failed", queued=False))

    return BatchIngestResult(
        accepted=accepted,
        duplicates=duplicates,
        failed=failed,
        results=results,
    )
