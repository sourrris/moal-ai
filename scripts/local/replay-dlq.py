#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os

import aio_pika
from aio_pika import DeliveryMode, Message


async def replay(limit: int, dry_run: bool, queue_name: str) -> int:
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    events_exchange_name = os.getenv("RABBITMQ_EVENTS_EXCHANGE", "risk.event.exchange")
    default_events_routing_key = os.getenv("RABBITMQ_EVENTS_ROUTING_KEY", "risk.event.ingested")
    default_events_v2_routing_key = os.getenv("RABBITMQ_EVENTS_V2_ROUTING_KEY", "risk.event.v2.ingested")

    connection = await aio_pika.connect_robust(rabbitmq_url)
    try:
        channel = await connection.channel(publisher_confirms=True)
        queue = await channel.declare_queue(queue_name, durable=True)
        events_exchange = await channel.get_exchange(events_exchange_name, ensure=True)

        replayed = 0
        while replayed < limit:
            try:
                message = await queue.get(timeout=1, fail=False)
            except asyncio.TimeoutError:
                break
            if message is None:
                break

            payload_text = message.body.decode("utf-8")
            try:
                payload_obj = json.loads(payload_text)
            except json.JSONDecodeError:
                payload_obj = {"raw": payload_text}

            inferred_key = message.routing_key or default_events_routing_key
            if isinstance(payload_obj, dict) and payload_obj.get("transaction"):
                inferred_key = default_events_v2_routing_key

            headers = dict(message.headers or {})
            headers["x-replay-count"] = int(headers.get("x-replay-count", 0)) + 1
            headers["x-replayed-from"] = queue_name

            if dry_run:
                await message.ack()
            else:
                outbound = Message(
                    body=message.body,
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    headers=headers,
                )
                await events_exchange.publish(outbound, routing_key=inferred_key)
                await message.ack()
            replayed += 1
        return replayed
    finally:
        await connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay messages from RabbitMQ DLQ to events exchange.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum messages to replay")
    parser.add_argument("--dry-run", action="store_true", help="Acknowledge messages without publishing")
    parser.add_argument("--queue", default=os.getenv("RABBITMQ_EVENTS_DLQ", "risk.event.dlq"), help="DLQ queue name")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    replayed = asyncio.run(replay(limit=max(1, args.limit), dry_run=args.dry_run, queue_name=args.queue))
    print(f"Replayed {replayed} message(s) from {args.queue}.")


if __name__ == "__main__":
    main()
