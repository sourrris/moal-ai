from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from risk_common.security import decode_access_token

from app.config import get_settings
from app.domain.connection_manager import ConnectionManager

router = APIRouter(tags=["notifications"])
settings = get_settings()
SUPPORTED_CHANNELS = {"alerts", "metrics"}


def _manager(websocket: WebSocket) -> ConnectionManager:
    return websocket.app.state.connection_manager


@router.websocket("/ws/alerts")
async def alerts_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    payload = None
    if token:
        payload = decode_access_token(token, settings.jwt_secret_key, settings.jwt_algorithm)

    if payload is None:
        await websocket.close(code=1008)
        return
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        await websocket.close(code=1008)
        return

    manager = _manager(websocket)
    await manager.connect(websocket, tenant_id=str(tenant_id), channels=["alerts"])
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.websocket("/ws/stream")
async def multiplexed_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    payload = None
    if token:
        payload = decode_access_token(token, settings.jwt_secret_key, settings.jwt_algorithm)

    if payload is None:
        await websocket.close(code=1008)
        return
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        await websocket.close(code=1008)
        return

    channels_query = websocket.query_params.get("channels", "alerts")
    requested_channels = [item.strip().lower() for item in channels_query.split(",") if item.strip()]
    channels = [item for item in requested_channels if item in SUPPORTED_CHANNELS]
    if not channels:
        channels = ["alerts"]

    manager = _manager(websocket)
    await manager.connect(websocket, tenant_id=str(tenant_id), channels=channels)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/v1/notifications/connections")
async def connection_count(request: Request) -> dict:
    manager: ConnectionManager = request.app.state.connection_manager
    return {
        "active_connections": manager.active_count,
        "channels": manager.channel_counts,
        "tenants": manager.tenant_channel_counts,
    }
