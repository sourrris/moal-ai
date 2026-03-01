from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from risk_common.logging import configure_logging
from risk_common.messaging import connect, setup_topology
from risk_common.schemas import HealthResponse

from app.api.notification_routes import router as notification_router
from app.application.bridge import NotificationBridge
from app.config import get_settings
from app.domain.connection_manager import ConnectionManager

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)

    rabbit_conn = await connect(settings.rabbitmq_url)
    rabbit_channel = await rabbit_conn.channel()
    await setup_topology(rabbit_channel, settings)

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)

    manager = ConnectionManager()
    bridge = NotificationBridge(
        redis_client=redis_client,
        rabbit_channel=rabbit_channel,
        manager=manager,
    )
    await bridge.start()

    app.state.rabbit_conn = rabbit_conn
    app.state.rabbit_channel = rabbit_channel
    app.state.redis_client = redis_client
    app.state.connection_manager = manager
    app.state.bridge = bridge

    try:
        yield
    finally:
        await bridge.stop()
        await redis_client.aclose()
        await rabbit_channel.close()
        await rabbit_conn.close()


app = FastAPI(title="AI Risk Notification Service", version="0.1.0", lifespan=lifespan)
app.include_router(notification_router)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    redis_client: Redis = app.state.redis_client
    await redis_client.ping()
    if getattr(app.state, "rabbit_channel", None) is None:
        raise RuntimeError("RabbitMQ channel unavailable")
    return HealthResponse(status="ready", service=settings.service_name)
