from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from risk_common.security import decode_access_token

from app.config import get_settings
from app.domain.connection_manager import ConnectionManager

router = APIRouter(tags=["notifications"])
settings = get_settings()
SUPPORTED_CHANNELS = {"alerts", "metrics"}


def _manager(websocket: WebSocket) -> ConnectionManager:
    return websocket.app.state.connection_manager


def _tenant_from_payload_or_query(payload: dict | None, websocket: WebSocket) -> str | None:
    tenant = payload.get("tenant_id") if isinstance(payload, dict) else None
    if tenant and isinstance(tenant, str):
        return tenant

    requested = websocket.query_params.get("tenant_id")
    if requested:
        requested = requested.strip()
        if requested and requested != "all":
            return requested
    return None


def _is_heartbeat_ping(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized == "ping" or normalized == '{"type":"ping"}'


def _resolve_channels(websocket: WebSocket) -> list[str]:
    channels_query = websocket.query_params.get("channels", "alerts")
    requested_channels = [item.strip().lower() for item in channels_query.split(",") if item.strip()]
    channels = [item for item in requested_channels if item in SUPPORTED_CHANNELS]
    return channels or ["alerts"]


async def _authorize_socket(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    payload = None
    if token:
        payload = decode_access_token(token, settings.jwt_verification_key, settings.jwt_algorithm)

    if payload is None:
        await websocket.close(code=1008)
        return
    tenant_id = _tenant_from_payload_or_query(payload, websocket)
    if not tenant_id:
        await websocket.close(code=1008)
        return None
    return str(tenant_id)


async def _run_stream(websocket: WebSocket, channels: list[str]) -> None:
    tenant_id = await _authorize_socket(websocket)
    if not tenant_id:
        return
    manager = _manager(websocket)
    await manager.connect(websocket, tenant_id=tenant_id, channels=channels)
    try:
        while True:
            message = await websocket.receive_text()
            if _is_heartbeat_ping(message):
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.websocket("/ws/alerts")
async def alerts_stream(websocket: WebSocket) -> None:
    await _run_stream(websocket, channels=["alerts"])


@router.websocket("/ws/stream")
async def multiplexed_stream(websocket: WebSocket) -> None:
    await _run_stream(websocket, channels=_resolve_channels(websocket))


@router.websocket("/ws/risk-stream")
async def risk_stream(websocket: WebSocket) -> None:
    await _run_stream(websocket, channels=_resolve_channels(websocket))


@router.get("/v1/notifications/connections")
async def connection_count(request: Request) -> dict:
    manager: ConnectionManager = request.app.state.connection_manager
    return {
        "active_connections": manager.active_count,
        "channels": manager.channel_counts,
        "tenants": manager.tenant_channel_counts,
    }
