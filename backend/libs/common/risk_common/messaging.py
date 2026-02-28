import json
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, IncomingMessage, Message


async def connect(url: str) -> aio_pika.RobustConnection:
    return await aio_pika.connect_robust(url)


async def setup_topology(channel: aio_pika.abc.AbstractChannel, settings) -> None:
    queue_args = {"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange}
    if getattr(settings, "rabbitmq_queue_type", "classic") == "quorum":
        queue_args["x-queue-type"] = "quorum"

    events_exchange = await channel.declare_exchange(
        settings.rabbitmq_events_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )
    alerts_exchange = await channel.declare_exchange(
        settings.rabbitmq_alerts_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )
    metrics_exchange = await channel.declare_exchange(
        settings.rabbitmq_metrics_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )
    reference_exchange = await channel.declare_exchange(
        settings.rabbitmq_reference_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )
    dlx_exchange = await channel.declare_exchange(
        settings.rabbitmq_dlx_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )

    events_queue = await channel.declare_queue(
        settings.rabbitmq_events_queue,
        durable=True,
        arguments=queue_args,
    )
    await events_queue.bind(events_exchange, routing_key=settings.rabbitmq_events_routing_key)

    events_v2_queue = await channel.declare_queue(
        settings.rabbitmq_events_v2_queue,
        durable=True,
        arguments=queue_args,
    )
    await events_v2_queue.bind(events_exchange, routing_key=settings.rabbitmq_events_v2_routing_key)

    alerts_queue = await channel.declare_queue(
        settings.rabbitmq_alerts_queue,
        durable=True,
        arguments=queue_args,
    )
    await alerts_queue.bind(alerts_exchange, routing_key=settings.rabbitmq_alerts_routing_key)

    metrics_queue = await channel.declare_queue(
        settings.rabbitmq_metrics_queue,
        durable=True,
        arguments=queue_args,
    )
    await metrics_queue.bind(metrics_exchange, routing_key=settings.rabbitmq_metrics_routing_key)

    reference_queue = await channel.declare_queue(
        settings.rabbitmq_reference_queue,
        durable=True,
        arguments=queue_args,
    )
    await reference_queue.bind(reference_exchange, routing_key=settings.rabbitmq_reference_routing_key)

    events_dlq = await channel.declare_queue(settings.rabbitmq_events_dlq, durable=True)
    await events_dlq.bind(dlx_exchange, routing_key=settings.rabbitmq_events_routing_key)
    await events_dlq.bind(dlx_exchange, routing_key=settings.rabbitmq_events_v2_routing_key)
    await events_dlq.bind(dlx_exchange, routing_key=settings.rabbitmq_metrics_routing_key)
    await events_dlq.bind(dlx_exchange, routing_key=settings.rabbitmq_reference_routing_key)


async def publish_json(
    channel: aio_pika.abc.AbstractChannel,
    exchange_name: str,
    routing_key: str,
    payload: dict,
    headers: dict | None = None,
) -> None:
    exchange = await channel.get_exchange(exchange_name)
    body = json.dumps(payload, default=str).encode("utf-8")
    message = Message(
        body=body,
        delivery_mode=DeliveryMode.PERSISTENT,
        content_type="application/json",
        headers=headers or {},
    )
    await exchange.publish(message, routing_key=routing_key)


async def consume(
    queue: aio_pika.abc.AbstractQueue,
    handler: Callable[[IncomingMessage], Awaitable[None]],
    prefetch: int = 50,
) -> None:
    await queue.channel.set_qos(prefetch_count=prefetch)
    await queue.consume(handler)
