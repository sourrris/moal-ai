from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from moal_common.schemas import AlertLifecycleUpdate, AlertResponse
from moal_common.schemas_v2 import AuthClaims
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    state: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    claims: AuthClaims = Depends(require_scope("alerts:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[AlertResponse]:
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if state:
        conditions.append("state = :state")
        params["state"] = state

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT * FROM alerts {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """
    result = await session.execute(text(query), params)
    rows = result.mappings().all()
    return [AlertResponse(**dict(row)) for row in rows]


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    payload: AlertLifecycleUpdate,
    claims: AuthClaims = Depends(require_scope("alerts:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertResponse:
    return await _transition_alert(session, alert_id, "acknowledged", payload.note)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: UUID,
    payload: AlertLifecycleUpdate,
    claims: AuthClaims = Depends(require_scope("alerts:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertResponse:
    return await _transition_alert(session, alert_id, "resolved", payload.note)


@router.post("/{alert_id}/false-positive", response_model=AlertResponse)
async def false_positive_alert(
    alert_id: UUID,
    payload: AlertLifecycleUpdate,
    claims: AuthClaims = Depends(require_scope("alerts:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AlertResponse:
    return await _transition_alert(session, alert_id, "false_positive", payload.note)


async def _transition_alert(
    session: AsyncSession,
    alert_id: UUID,
    next_state: str,
    note: str | None,
) -> AlertResponse:
    result = await session.execute(
        text("""
            UPDATE alerts
            SET state = :state, note = COALESCE(:note, note), updated_at = NOW()
            WHERE alert_id = :alert_id
            RETURNING *
        """),
        {"alert_id": str(alert_id), "state": next_state, "note": note},
    )
    row = result.mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    await session.commit()
    return AlertResponse(**dict(row))
