from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.feature_enrichment_service import EnrichmentRequest, FeatureEnrichmentService
from app.infrastructure.db import get_session

router = APIRouter(prefix="/v1/enrichment", tags=["enrichment"])


@router.post("/resolve")
async def resolve_features(
    payload: EnrichmentRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await FeatureEnrichmentService.enrich(session, payload)
    return {"tenant_id": payload.tenant_id, **result}
