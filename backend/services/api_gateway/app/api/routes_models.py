from fastapi import APIRouter, Depends

from app.api.deps import get_current_subject
from app.application.services import ModelManagementService

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
