from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from moal_common.logging import configure_logging
from moal_common.schemas import HealthResponse

from app.api import (
    routes_alerts_v2,
    routes_auth,
    routes_dashboard,
    routes_events_v2,
    routes_models_v2,
    routes_overview,
)
from app.config import get_settings
from app.infrastructure.db import check_db_health

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    yield


app = FastAPI(title="moal-ai API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes_auth.router)
app.include_router(routes_overview.router)
app.include_router(routes_dashboard.router)
app.include_router(routes_events_v2.router)
app.include_router(routes_alerts_v2.router)
app.include_router(routes_models_v2.router)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    await check_db_health()
    return HealthResponse(status="ready", service=settings.service_name)
