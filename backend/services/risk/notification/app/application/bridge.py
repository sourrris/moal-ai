import asyncio
import json

from aio_pika import IncomingMessage
from redis.asyncio import Redis

from app.config import get_settings
from app.domain.connection_manager import ConnectionManager

settings = get_settings()


class NotificationBridge:
    def __init__(self, redis_client: Redis, rabbit_channel, manager: ConnectionManager):
        self.redis_client = redis_client
        self.rabbit_channel = rabbit_channel
        self.manager = manager
        self.queue = None
        self.consumer_tag: str | None = None
        self.metrics_queue = None
        self.metrics_consumer_tag: str | None = None
        self.pubsub = None
        self.redis_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.queue = await self.rabbit_channel.declare_queue(
            settings.rabbitmq_alerts_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange},
        )
        self.consumer_tag = await self.queue.consume(self._on_rabbit_alert)
        self.metrics_queue = await self.rabbit_channel.declare_queue(
            settings.rabbitmq_metrics_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange},
        )
        self.metrics_consumer_tag = await self.metrics_queue.consume(self._on_rabbit_metric)

        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe(settings.redis_alert_channel)
        await self.pubsub.subscribe(settings.redis_metrics_channel)
        await self.pubsub.subscribe(settings.redis_alert_channel_legacy)
        await self.pubsub.subscribe(settings.redis_metrics_channel_legacy)
        self.redis_task = asyncio.create_task(self._fanout_loop())

    async def stop(self) -> None:
        if self.queue is not None and self.consumer_tag is not None:
            await self.queue.cancel(self.consumer_tag)
        if self.metrics_queue is not None and self.metrics_consumer_tag is not None:
            await self.metrics_queue.cancel(self.metrics_consumer_tag)

        if self.redis_task is not None:
            self.redis_task.cancel()
            try:
                await self.redis_task
            except asyncio.CancelledError:
                pass

        if self.pubsub is not None:
            await self.pubsub.unsubscribe(settings.redis_alert_channel)
            await self.pubsub.unsubscribe(settings.redis_metrics_channel)
            await self.pubsub.unsubscribe(settings.redis_alert_channel_legacy)
            await self.pubsub.unsubscribe(settings.redis_metrics_channel_legacy)
            await self.pubsub.aclose()

    async def _on_rabbit_alert(self, message: IncomingMessage) -> None:
        body = message.body.decode("utf-8")
        await self.redis_client.publish(settings.redis_alert_channel, body)
        await self.redis_client.publish(settings.redis_alert_channel_legacy, body)
        await message.ack()

    async def _on_rabbit_metric(self, message: IncomingMessage) -> None:
        body = message.body.decode("utf-8")
        await self.redis_client.publish(settings.redis_metrics_channel, body)
        await self.redis_client.publish(settings.redis_metrics_channel_legacy, body)
        await message.ack()

    async def _fanout_loop(self) -> None:
        if self.pubsub is None:
            return

        async for msg in self.pubsub.listen():
            if msg.get("type") != "message":
                continue

            data = msg.get("data", "")
            channel = msg.get("channel", "")
            if isinstance(channel, bytes):
                channel_name = channel.decode("utf-8")
            else:
                channel_name = str(channel)

            if isinstance(data, bytes):
                payload = data.decode("utf-8")
            else:
                payload = str(data)

            metric_channels = {settings.redis_metrics_channel, settings.redis_metrics_channel_legacy}
            stream_channel = "metrics" if channel_name in metric_channels else "alerts"
            tenant_id = self._extract_tenant_id(payload)
            if not tenant_id:
                continue
            await self.manager.broadcast(payload, tenant_id=tenant_id, channel=stream_channel)

    @staticmethod
    def _extract_tenant_id(payload: str) -> str | None:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None

        if isinstance(parsed, dict):
            if isinstance(parsed.get("tenant_id"), str):
                return parsed["tenant_id"]
            data = parsed.get("data")
            if isinstance(data, dict) and isinstance(data.get("tenant_id"), str):
                return data["tenant_id"]
        return None
