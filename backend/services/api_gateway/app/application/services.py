import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.repositories import EventRepository
from risk_common.schemas import EventEnvelope

logger = logging.getLogger(__name__)
settings = get_settings()


class EventIngestionService:
    @staticmethod
    async def persist_event(
        session: AsyncSession,
        event: EventEnvelope,
        submitted_by: str,
    ) -> bool:
        return await EventRepository.create_if_absent(session, event=event, submitted_by=submitted_by)


class ModelManagementService:
    @staticmethod
    async def get_active_model() -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.ml_inference_url}/v1/models/active")
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def list_all_models() -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.ml_inference_url}/v1/models")
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def train_model(payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(f"{settings.ml_inference_url}/v1/models/train", json=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def activate_model(payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{settings.ml_inference_url}/v1/models/activate", json=payload)
            response.raise_for_status()
            return response.json()
