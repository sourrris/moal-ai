import json
import logging
from uuid import UUID

import httpx
from aio_pika import IncomingMessage
from redis.asyncio import Redis

from app.config import get_settings
from app.infrastructure.db import SessionLocal
from app.infrastructure.repository import mark_failed, persist_inference
from risk_common.messaging import publish_json
from risk_common.schemas import AlertMessage, EventEnvelope, InferenceRequest, InferenceResponse

logger = logging.getLogger(__name__)
settings = get_settings()


class EventProcessor:
    def __init__(self, redis_client: Redis, rabbit_channel):
        self.redis = redis_client
        self.rabbit_channel = rabbit_channel

    async def handle_message(self, message: IncomingMessage) -> None:
        event_id: UUID | None = None
        payload: dict | None = None

        try:
            payload = json.loads(message.body)
            event = EventEnvelope(**payload)
            event_id = event.event_id

            processed_key = f"processed:{event.event_id}"
            if await self.redis.get(processed_key):
                await message.ack()
                return

            inference = await self._call_inference(event)

            async with SessionLocal() as session:
                await persist_inference(
                    session=session,
                    event_id=event.event_id,
                    model_name=inference.model_name,
                    model_version=inference.model_version,
                    score=inference.anomaly_score,
                    threshold=inference.threshold,
                    is_anomaly=inference.is_anomaly,
                )

            if inference.is_anomaly:
                alert = AlertMessage(
                    event_id=event.event_id,
                    tenant_id=event.tenant_id,
                    model_name=inference.model_name,
                    model_version=inference.model_version,
                    anomaly_score=inference.anomaly_score,
                    threshold=inference.threshold,
                )
                await publish_json(
                    channel=self.rabbit_channel,
                    exchange_name=settings.rabbitmq_alerts_exchange,
                    routing_key=settings.rabbitmq_alerts_routing_key,
                    payload=alert.model_dump(mode="json"),
                )

            await self.redis.set(processed_key, "1", ex=settings.dedupe_ttl_seconds)
            await message.ack()

        except Exception as exc:  # noqa: BLE001
            logger.exception("worker_process_failed", extra={"error": str(exc)})
            await self._retry_or_dead_letter(message, payload, event_id)

    async def _call_inference(self, event: EventEnvelope) -> InferenceResponse:
        req = InferenceRequest(event_id=event.event_id, tenant_id=event.tenant_id, features=event.features)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{settings.ml_inference_url}/v1/infer",
                json=req.model_dump(mode="json"),
            )
            response.raise_for_status()
            return InferenceResponse(**response.json())

    async def _retry_or_dead_letter(
        self,
        message: IncomingMessage,
        payload: dict | None,
        event_id: UUID | None,
    ) -> None:
        headers = dict(message.headers or {})
        retry_count = int(headers.get("x-retry-count", 0))

        if payload is None:
            await message.ack()
            return

        if retry_count < settings.max_event_retries:
            headers["x-retry-count"] = retry_count + 1
            await publish_json(
                channel=self.rabbit_channel,
                exchange_name=settings.rabbitmq_events_exchange,
                routing_key=settings.rabbitmq_events_routing_key,
                payload=payload,
                headers=headers,
            )
            await message.ack()
            return

        await publish_json(
            channel=self.rabbit_channel,
            exchange_name=settings.rabbitmq_dlx_exchange,
            routing_key=settings.rabbitmq_events_routing_key,
            payload=payload,
            headers={"x-dead-letter-reason": "max-retries-exceeded"},
        )

        if event_id is not None:
            async with SessionLocal() as session:
                await mark_failed(session, event_id)

        await message.ack()
