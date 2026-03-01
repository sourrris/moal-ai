import json
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, IncomingMessage, Message


async def connect(url: str) -> aio_pika.RobustConnection:
    return await aio_pika.connect_robust(url)


def _unique(*values: str) -> list[str]:
    ordered: list[str] = []
    for value in values:
        if value and value not in ordered:
            ordered.append(value)
    return ordered


async def _declare_exchanges(
    channel: aio_pika.abc.AbstractChannel,
    names: list[str],
) -> dict[str, aio_pika.abc.AbstractExchange]:
    exchanges: dict[str, aio_pika.abc.AbstractExchange] = {}
    for name in names:
        exchanges[name] = await channel.declare_exchange(name, ExchangeType.TOPIC, durable=True)
    return exchanges


async def _declare_and_bind_queue(
    channel: aio_pika.abc.AbstractChannel,
    *,
    queue_names: list[str],
    exchange_names: list[str],
    routing_keys: list[str],
    queue_args: dict | None = None,
    queue_args_by_name: dict[str, dict] | None = None,
) -> None:
    default_queue_args = queue_args or {}
    per_queue_args = queue_args_by_name or {}
    for queue_name in queue_names:
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments=per_queue_args.get(queue_name, default_queue_args),
        )
        for exchange_name in exchange_names:
            exchange = await channel.get_exchange(exchange_name)
            for routing_key in routing_keys:
                await queue.bind(exchange, routing_key=routing_key)


async def setup_topology(channel: aio_pika.abc.AbstractChannel, settings) -> None:
    queue_args_primary = {"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange}
    queue_args_legacy = {"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange_legacy}
    if getattr(settings, "rabbitmq_queue_type", "classic") == "quorum":
        queue_args_primary["x-queue-type"] = "quorum"
        queue_args_legacy["x-queue-type"] = "quorum"

    events_exchange_names = _unique(settings.rabbitmq_events_exchange, settings.rabbitmq_events_exchange_legacy)
    alerts_exchange_names = _unique(settings.rabbitmq_alerts_exchange, settings.rabbitmq_alerts_exchange_legacy)
    metrics_exchange_names = _unique(settings.rabbitmq_metrics_exchange, settings.rabbitmq_metrics_exchange_legacy)
    reference_exchange_names = _unique(settings.rabbitmq_reference_exchange, settings.rabbitmq_reference_exchange_legacy)
    dlx_exchange_names = _unique(settings.rabbitmq_dlx_exchange, settings.rabbitmq_dlx_exchange_legacy)

    await _declare_exchanges(
        channel,
        _unique(
            *events_exchange_names,
            *alerts_exchange_names,
            *metrics_exchange_names,
            *reference_exchange_names,
            *dlx_exchange_names,
        ),
    )

    await _declare_and_bind_queue(
        channel,
        queue_names=_unique(settings.rabbitmq_events_queue, settings.rabbitmq_events_queue_legacy),
        exchange_names=events_exchange_names,
        routing_keys=_unique(settings.rabbitmq_events_routing_key, settings.rabbitmq_events_routing_key_legacy),
        queue_args_by_name={
            settings.rabbitmq_events_queue: queue_args_primary,
            settings.rabbitmq_events_queue_legacy: queue_args_legacy,
        },
    )
    await _declare_and_bind_queue(
        channel,
        queue_names=_unique(settings.rabbitmq_events_v2_queue, settings.rabbitmq_events_v2_queue_legacy),
        exchange_names=events_exchange_names,
        routing_keys=_unique(settings.rabbitmq_events_v2_routing_key, settings.rabbitmq_events_v2_routing_key_legacy),
        queue_args_by_name={
            settings.rabbitmq_events_v2_queue: queue_args_primary,
            settings.rabbitmq_events_v2_queue_legacy: queue_args_legacy,
        },
    )
    await _declare_and_bind_queue(
        channel,
        queue_names=_unique(settings.rabbitmq_alerts_queue, settings.rabbitmq_alerts_queue_legacy),
        exchange_names=alerts_exchange_names,
        routing_keys=_unique(settings.rabbitmq_alerts_routing_key, settings.rabbitmq_alerts_routing_key_legacy),
        queue_args_by_name={
            settings.rabbitmq_alerts_queue: queue_args_primary,
            settings.rabbitmq_alerts_queue_legacy: queue_args_legacy,
        },
    )
    await _declare_and_bind_queue(
        channel,
        queue_names=_unique(settings.rabbitmq_metrics_queue, settings.rabbitmq_metrics_queue_legacy),
        exchange_names=metrics_exchange_names,
        routing_keys=_unique(settings.rabbitmq_metrics_routing_key, settings.rabbitmq_metrics_routing_key_legacy),
        queue_args_by_name={
            settings.rabbitmq_metrics_queue: queue_args_primary,
            settings.rabbitmq_metrics_queue_legacy: queue_args_legacy,
        },
    )
    await _declare_and_bind_queue(
        channel,
        queue_names=_unique(settings.rabbitmq_reference_queue, settings.rabbitmq_reference_queue_legacy),
        exchange_names=reference_exchange_names,
        routing_keys=_unique(settings.rabbitmq_reference_routing_key, settings.rabbitmq_reference_routing_key_legacy),
        queue_args_by_name={
            settings.rabbitmq_reference_queue: queue_args_primary,
            settings.rabbitmq_reference_queue_legacy: queue_args_legacy,
        },
    )

    for dlq_name in _unique(settings.rabbitmq_events_dlq, settings.rabbitmq_events_dlq_legacy):
        events_dlq = await channel.declare_queue(dlq_name, durable=True)
        for dlx_exchange_name in dlx_exchange_names:
            dlx_exchange = await channel.get_exchange(dlx_exchange_name)
            for routing_key in _unique(
                settings.rabbitmq_events_routing_key,
                settings.rabbitmq_events_routing_key_legacy,
                settings.rabbitmq_events_v2_routing_key,
                settings.rabbitmq_events_v2_routing_key_legacy,
                settings.rabbitmq_metrics_routing_key,
                settings.rabbitmq_metrics_routing_key_legacy,
                settings.rabbitmq_reference_routing_key,
                settings.rabbitmq_reference_routing_key_legacy,
            ):
                await events_dlq.bind(dlx_exchange, routing_key=routing_key)


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


async def publish_json_with_compat(
    channel: aio_pika.abc.AbstractChannel,
    *,
    exchange_name: str,
    routing_key: str,
    payload: dict,
    headers: dict | None = None,
    legacy_exchange_name: str | None = None,
    legacy_routing_key: str | None = None,
) -> None:
    await publish_json(
        channel=channel,
        exchange_name=exchange_name,
        routing_key=routing_key,
        payload=payload,
        headers=headers,
    )
    if legacy_exchange_name and legacy_routing_key:
        if legacy_exchange_name != exchange_name or legacy_routing_key != routing_key:
            await publish_json(
                channel=channel,
                exchange_name=legacy_exchange_name,
                routing_key=legacy_routing_key,
                payload=payload,
                headers=headers,
            )


async def consume(
    queue: aio_pika.abc.AbstractQueue,
    handler: Callable[[IncomingMessage], Awaitable[None]],
    prefetch: int = 50,
) -> None:
    await queue.channel.set_qos(prefetch_count=prefetch)
    await queue.consume(handler)
