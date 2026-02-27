from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_subject
from app.application.services import ModelManagementService
from app.infrastructure.db import get_db_session
from app.infrastructure.repositories import ModelRepository

router = APIRouter(prefix="/v1/models", tags=["models"])


@router.get("/active")
async def get_active_model(_: str = Depends(get_current_subject)) -> dict:
    return await ModelManagementService.get_active_model()


@router.post("/train")
async def train_model(payload: dict, _: str = Depends(get_current_subject)) -> dict:
    return await ModelManagementService.train_model(payload)


@router.post("/activate")
async def activate_model(payload: dict, _: str = Depends(get_current_subject)) -> dict:
    return await ModelManagementService.activate_model(payload)


@router.get("")
async def list_models(
    _: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        active = await ModelManagementService.get_active_model()
    except Exception:  # noqa: BLE001
        active = {}
    active_version = active.get("model_version")
    active_name = active.get("model_name")

    models = await ModelRepository.list_models(session)
    for item in models:
        item["active"] = item.get("model_version") == active_version and item.get("model_name") == active_name

    return {"active_model": active, "items": models}


@router.get("/{model_version}/metrics")
async def model_metrics(
    model_version: str,
    _: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await ModelRepository.model_metrics(session, model_version)
