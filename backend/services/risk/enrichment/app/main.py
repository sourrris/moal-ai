import sentry_sdk
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from moal_common.logging import configure_logging
from moal_common.schemas import HealthResponse

from app.api.enrichment_routes import router as enrichment_router
from app.config import get_settings
from app.infrastructure.db import db_ready

settings = get_settings()
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.environment,
    )

configure_logging(settings.log_level)

app = FastAPI(title="AI Risk Feature Enrichment", version="0.1.0")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.include_router(enrichment_router)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await db_ready()
    return HealthResponse(status="ready", service=settings.service_name)
