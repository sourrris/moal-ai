from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from moal_common.logging import configure_logging
from moal_common.schemas import HealthResponse

from app.api.routes_control import router as control_router
from app.config import get_settings
from app.infrastructure.db import check_db_health

settings = get_settings()
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.environment,
    )


def _cors_origins() -> list[str]:
    raw = getattr(settings, "cors_allow_origins", "http://control.localhost,http://ops-control.localhost")
    return [origin.strip() for origin in str(raw).split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    yield


app = FastAPI(title="Aegis Control Plane API", version="0.1.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(control_router)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await check_db_health()
    return HealthResponse(status="ready", service=settings.service_name)
