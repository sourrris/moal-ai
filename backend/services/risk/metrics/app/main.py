from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from risk_common.logging import configure_logging
from risk_common.schemas import HealthResponse

from app.application.aggregator import MetricsAggregator
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
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await db_ready()
    redis_client: Redis = app.state.redis_client
    await redis_client.ping()
    return HealthResponse(status="ready", service=settings.service_name)
