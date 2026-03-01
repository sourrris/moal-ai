import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.monitoring_repository import EventRepository
from risk_common.schemas import EventEnvelope

logger = logging.getLogger(__name__)
settings = get_settings()


class ModelGatewayError(RuntimeError):
    def __init__(self, *, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Model service request failed ({status_code}): {detail}")


def _error_detail_from_response(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    if isinstance(payload, dict) and "detail" in payload:
        return payload["detail"]
    return payload


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
            if response.is_error:
                raise ModelGatewayError(status_code=response.status_code, detail=_error_detail_from_response(response))
            return response.json()

    @staticmethod
    async def list_all_models() -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.ml_inference_url}/v1/models")
            if response.is_error:
                raise ModelGatewayError(status_code=response.status_code, detail=_error_detail_from_response(response))
            return response.json()

    @staticmethod
    async def train_model(payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(f"{settings.ml_inference_url}/v1/models/train", json=payload)
            if response.is_error:
                raise ModelGatewayError(status_code=response.status_code, detail=_error_detail_from_response(response))
            return response.json()

    @staticmethod
    async def activate_model(payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{settings.ml_inference_url}/v1/models/activate", json=payload)
            if response.is_error:
                raise ModelGatewayError(status_code=response.status_code, detail=_error_detail_from_response(response))
            return response.json()
