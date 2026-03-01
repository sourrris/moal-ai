from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request

from app.application.service import InferenceService
from risk_common.schemas import InferenceRequest, InferenceResponse, ModelMetadata, ModelTrainingResult, ModelTrainRequest

router = APIRouter(prefix="/v1", tags=["ml"])


class ActivateModelRequest(BaseModel):
    model_name: str
    model_version: str


def get_service(request: Request) -> InferenceService:
    return request.app.state.inference_service


@router.post("/infer", response_model=InferenceResponse)
async def infer(payload: InferenceRequest, request: Request) -> InferenceResponse:
    service = get_service(request)
    try:
        return await service.infer(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/train", response_model=ModelTrainingResult)
async def train_model(payload: ModelTrainRequest, request: Request) -> ModelTrainingResult:
    service = get_service(request)
    try:
        return await service.train(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/activate", response_model=ModelMetadata)
async def activate_model(payload: ActivateModelRequest, request: Request) -> ModelMetadata:
    service = get_service(request)
    try:
        return await service.activate(model_name=payload.model_name, model_version=payload.model_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/models", response_model=list[ModelMetadata])
async def list_models(request: Request) -> list[ModelMetadata]:
    service = get_service(request)
    return service.list_models()


@router.get("/models/active", response_model=ModelMetadata)
async def active_model(request: Request) -> ModelMetadata:
    service = get_service(request)
    return service.get_active()
