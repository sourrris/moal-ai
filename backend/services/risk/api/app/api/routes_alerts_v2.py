from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from risk_common.schemas_v2 import AlertLifecycleUpdate, AlertV2, AuthClaims
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.infrastructure.db import get_db_session
from app.infrastructure.operational_repository_v2 import AlertV2Repository

router = APIRouter(prefix="/v2/alerts", tags=["alerts-v2"])


@router.get("")
async def list_alerts_v2(
    state: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    claims: AuthClaims = Depends(require_scope("alerts:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await AlertV2Repository.list_alerts(
        session,
        tenant_id=claims.tenant_id,
        state=state,
        cursor=cursor,
        limit=limit,
    )


@router.post("/{alert_id}/ack", response_model=AlertV2)
async def acknowledge_alert_v2(
    alert_id: UUID,
    payload: AlertLifecycleUpdate,
    claims: AuthClaims = Depends(require_scope("alerts:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertV2:
    item = await AlertV2Repository.transition_alert(
        session,
        tenant_id=claims.tenant_id,
        alert_id=alert_id,
        next_state="acknowledged",
        actor_id=claims.sub,
        note=payload.note,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertV2(**item)


@router.post("/{alert_id}/resolve", response_model=AlertV2)
async def resolve_alert_v2(
    alert_id: UUID,
    payload: AlertLifecycleUpdate,
    claims: AuthClaims = Depends(require_scope("alerts:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertV2:
    item = await AlertV2Repository.transition_alert(
        session,
        tenant_id=claims.tenant_id,
        alert_id=alert_id,
        next_state="resolved",
        actor_id=claims.sub,
        note=payload.note,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertV2(**item)


@router.post("/{alert_id}/false-positive", response_model=AlertV2)
async def false_positive_alert_v2(
    alert_id: UUID,
    payload: AlertLifecycleUpdate,
    claims: AuthClaims = Depends(require_scope("alerts:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertV2:
    item = await AlertV2Repository.transition_alert(
        session,
        tenant_id=claims.tenant_id,
        alert_id=alert_id,
        next_state="false_positive",
        actor_id=claims.sub,
        note=payload.note,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertV2(**item)
