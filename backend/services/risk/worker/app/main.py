from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis

from app.application.processor import EventProcessor
from app.config import get_settings
from app.infrastructure.db import db_ready
from risk_common.logging import configure_logging
from risk_common.messaging import connect, setup_topology
from risk_common.schemas import HealthResponse

settings = get_settings()
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.environment,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)

    rabbit_conn = await connect(
        settings.rabbitmq_url,
        heartbeat=settings.rabbitmq_heartbeat_seconds,
        connection_timeout=float(settings.rabbitmq_connection_timeout_seconds),
    )
    rabbit_channel = await rabbit_conn.channel()
    await setup_topology(rabbit_channel, settings)

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)

    processor = EventProcessor(redis_client=redis_client, rabbit_channel=rabbit_channel)
    events_queue = await rabbit_channel.declare_queue(
        settings.rabbitmq_events_queue,
        durable=True,
        arguments={"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange},
    )
    consumer_tag = await events_queue.consume(processor.handle_message)
    events_v2_queue = await rabbit_channel.declare_queue(
        settings.rabbitmq_events_v2_queue,
        durable=True,
        arguments={"x-dead-letter-exchange": settings.rabbitmq_dlx_exchange},
    )
    consumer_tag_v2 = await events_v2_queue.consume(processor.handle_message_v2)

    app.state.rabbit_conn = rabbit_conn
    app.state.rabbit_channel = rabbit_channel
    app.state.redis_client = redis_client
    app.state.events_queue = events_queue
    app.state.consumer_tag = consumer_tag
    app.state.events_v2_queue = events_v2_queue
    app.state.consumer_tag_v2 = consumer_tag_v2

    try:
        yield
    finally:
        await app.state.events_queue.cancel(app.state.consumer_tag)
        await app.state.events_v2_queue.cancel(app.state.consumer_tag_v2)
        await redis_client.aclose()
        await rabbit_channel.close()
        await rabbit_conn.close()


app = FastAPI(title="AI Risk Event Worker", version="0.1.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await db_ready()
    redis_client: Redis = app.state.redis_client
    await redis_client.ping()
    if getattr(app.state, "rabbit_channel", None) is None:
        raise RuntimeError("RabbitMQ channel unavailable")
    return HealthResponse(status="ready", service=settings.service_name)
