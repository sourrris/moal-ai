import asyncio

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
        self.pubsub = None
        self.redis_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.queue = await self.rabbit_channel.declare_queue(
            settings.rabbitmq_alerts_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange},
        )
        self.consumer_tag = await self.queue.consume(self._on_rabbit_alert)

        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe(settings.redis_alert_channel)
        self.redis_task = asyncio.create_task(self._fanout_loop())

    async def stop(self) -> None:
        if self.queue is not None and self.consumer_tag is not None:
            await self.queue.cancel(self.consumer_tag)

        if self.redis_task is not None:
            self.redis_task.cancel()
            try:
                await self.redis_task
            except asyncio.CancelledError:
                pass

        if self.pubsub is not None:
            await self.pubsub.unsubscribe(settings.redis_alert_channel)
            await self.pubsub.aclose()

    async def _on_rabbit_alert(self, message: IncomingMessage) -> None:
        body = message.body.decode("utf-8")
        await self.redis_client.publish(settings.redis_alert_channel, body)
        await message.ack()

    async def _fanout_loop(self) -> None:
        if self.pubsub is None:
            return

        async for msg in self.pubsub.listen():
            if msg.get("type") != "message":
                continue

            data = msg.get("data", "")
            if isinstance(data, bytes):
                payload = data.decode("utf-8")
            else:
                payload = str(data)

            await self.manager.broadcast(payload)
