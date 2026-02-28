from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.application.aggregator import MetricsAggregator
from app.config import get_settings
from app.infrastructure.db import SessionLocal, db_ready
from risk_common.logging import configure_logging
from risk_common.schemas import HealthResponse

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    aggregator = MetricsAggregator(session_factory=SessionLocal, redis_client=redis_client)
    await aggregator.start()

    app.state.redis_client = redis_client
    app.state.aggregator = aggregator

    try:
        yield
    finally:
        await aggregator.stop()
        await redis_client.aclose()


app = FastAPI(title="AI Risk Metrics Aggregator", version="0.1.0", lifespan=lifespan)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await db_ready()
    redis_client: Redis = app.state.redis_client
    await redis_client.ping()
    return HealthResponse(status="ready", service=settings.service_name)
