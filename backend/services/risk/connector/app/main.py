from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from risk_common.logging import configure_logging
from risk_common.messaging import connect, setup_topology
from risk_common.schemas import HealthResponse

from app.api.connector_routes import router as connectors_router
from app.application.scheduler import ConnectorScheduler
from app.config import get_settings
from app.infrastructure.db import SessionLocal, db_ready

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

    scheduler = ConnectorScheduler(rabbit_channel=rabbit_channel)
    await scheduler.start()

    app.state.rabbit_conn = rabbit_conn
    app.state.rabbit_channel = rabbit_channel
    app.state.scheduler = scheduler
    app.state.db_session_factory = SessionLocal

    try:
        yield
    finally:
        await scheduler.stop()
        await rabbit_channel.close()
        await rabbit_conn.close()


app = FastAPI(title="AI Risk Data Connector Service", version="0.1.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.include_router(connectors_router)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await db_ready()
    if getattr(app.state, "rabbit_channel", None) is None:
        raise RuntimeError("RabbitMQ channel unavailable")
    return HealthResponse(status="ready", service=settings.service_name)
