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

    # Get all models known to ML service
    try:
        ml_models = await ModelManagementService.list_all_models()
    except Exception:  # noqa: BLE001
        ml_models = []

    # Get stats from DB
    stats_list = await ModelRepository.list_models(session)
    stats_map = {(s["model_name"], s["model_version"]): s for s in stats_list}

    merged = []
    for m in ml_models:
        key = (m["model_name"], m["model_version"])
        stats = stats_map.get(key, {})
        merged.append({
            "model_name": m["model_name"],
            "model_version": m["model_version"],
            "threshold": stats.get("threshold") or m.get("threshold"),
            "updated_at": stats.get("updated_at") or m.get("updated_at"),
            "inference_count": stats.get("inference_count") or 0,
            "anomaly_rate": stats.get("anomaly_rate") or 0,
            "active": m.get("model_version") == active_version and m.get("model_name") == active_name
        })

    # Add any models that only exist in DB (unlikely but possible)
    existing_keys = {(m["model_name"], m["model_version"]) for m in merged}
    for s in stats_list:
        if (s["model_name"], s["model_version"]) not in existing_keys:
            s["active"] = s.get("model_version") == active_version and s.get("model_name") == active_name
            merged.append(s)

    return {"active_model": active, "items": merged}


@router.get("/{model_version}/metrics")
async def model_metrics(
    model_version: str,
    _: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await ModelRepository.model_metrics(session, model_version)
