from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.infrastructure.db import get_db_session
from app.infrastructure.operational_repository_v2 import RiskDecisionRepository
from risk_common.schemas_v2 import AuthClaims, RiskDecisionV2

router = APIRouter(prefix="/v2/risk-decisions", tags=["risk-decisions-v2"])


@router.get("/{event_id}", response_model=RiskDecisionV2)
async def fetch_risk_decision_v2(
    event_id: UUID,
    claims: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> RiskDecisionV2:
    item = await RiskDecisionRepository.fetch_by_event_id(
        session,
        tenant_id=claims.tenant_id,
        event_id=event_id,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Decision not found")
    return RiskDecisionV2(**item)
