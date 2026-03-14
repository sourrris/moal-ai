from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from risk_common.logging import configure_logging
from risk_common.messaging import connect, setup_topology
from risk_common.schemas import HealthResponse

from app.application.router import AlertRouter
from app.config import get_settings
from app.infrastructure.db import check_db_health

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
    rabbit_channel = await rabbit_conn.channel(publisher_confirms=True)
    await setup_topology(rabbit_channel, settings)

    router = AlertRouter(rabbit_channel)
    await router.start()

    app.state.rabbit_conn = rabbit_conn
    app.state.rabbit_channel = rabbit_channel
    app.state.alert_router = router

    try:
        yield
    finally:
        await router.stop()
        await rabbit_channel.close()
        await rabbit_conn.close()


app = FastAPI(title="Aegis Alert Router", version="0.1.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await check_db_health()
    if getattr(app.state, "rabbit_channel", None) is None:
        raise RuntimeError("RabbitMQ channel unavailable")
    return HealthResponse(status="ready", service=settings.service_name)
