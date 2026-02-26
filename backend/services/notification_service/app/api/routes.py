from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.domain.connection_manager import ConnectionManager
from risk_common.security import decode_access_token

router = APIRouter(tags=["notifications"])
settings = get_settings()


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

    manager = _manager(websocket)
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/v1/notifications/connections")
async def connection_count(request: Request) -> dict:
    return {"active_connections": request.app.state.connection_manager.active_count}
