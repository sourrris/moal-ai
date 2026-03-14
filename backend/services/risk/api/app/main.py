from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api import (
    routes_alerts,
    routes_auth,
    routes_auth_v2,
    routes_events,
    routes_models,
    routes_overview,
    routes_alerts_v2,
    routes_data_sources_v2,
    routes_events_v2,
    routes_models_v2,
    routes_risk_decisions_v2,
    routes_setup,
    routes_platform_v1,
)
from app.config import get_settings
from app.infrastructure.db import check_db_health
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
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


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

    app.state.rabbit_conn = rabbit_conn
    app.state.rabbit_channel = rabbit_channel

    try:
        yield
    finally:
        await rabbit_channel.close()
        await rabbit_conn.close()


app = FastAPI(title="AI Risk API Gateway", version="0.1.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes_auth.router)
app.include_router(routes_auth_v2.router)
app.include_router(routes_overview.router)
app.include_router(routes_alerts.router)
app.include_router(routes_events.router)
app.include_router(routes_models.router)
app.include_router(routes_events_v2.router)
app.include_router(routes_alerts_v2.router)
app.include_router(routes_risk_decisions_v2.router)
app.include_router(routes_data_sources_v2.router)
app.include_router(routes_models_v2.router)
app.include_router(routes_setup.router)
app.include_router(routes_platform_v1.router)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await check_db_health()
    channel_ok = getattr(app.state, "rabbit_channel", None) is not None
    if not channel_ok:
        raise RuntimeError("RabbitMQ channel unavailable")
    return HealthResponse(status="ready", service=settings.service_name)
