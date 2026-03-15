from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from risk_common.logging import configure_logging
from risk_common.schemas import HealthResponse

from app.api.model_routes import router as ml_router
from app.application.model_inference_service import InferenceService
from app.config import get_settings
from app.infrastructure.model_store import ModelStore

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
    model_store = ModelStore(settings.model_dir, settings.default_model_name)
    await model_store.initialize()

    app.state.model_store = model_store
    app.state.inference_service = InferenceService(model_store=model_store)
    yield


app = FastAPI(title="AI Risk ML Inference", version="0.1.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.include_router(ml_router)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready() -> HealthResponse:
    if getattr(app.state, "inference_service", None) is None:
        raise RuntimeError("Inference service unavailable")
    return HealthResponse(status="ready", service=settings.service_name)
