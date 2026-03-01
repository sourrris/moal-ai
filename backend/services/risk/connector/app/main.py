from contextlib import asynccontextmanager

from fastapi import FastAPI
from risk_common.logging import configure_logging
from risk_common.messaging import connect, setup_topology
from risk_common.schemas import HealthResponse

from app.api.connector_routes import router as connectors_router
from app.application.scheduler import ConnectorScheduler
from app.config import get_settings
from app.infrastructure.db import SessionLocal, db_ready

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)

    rabbit_conn = await connect(settings.rabbitmq_url)
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
