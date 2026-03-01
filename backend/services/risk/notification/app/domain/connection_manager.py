from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._tenant_channel_connections: dict[str, dict[str, set[WebSocket]]] = {}
        self._socket_context: dict[WebSocket, tuple[str, set[str]]] = {}

    async def connect(self, websocket: WebSocket, *, tenant_id: str, channels: list[str] | None = None) -> None:
        await websocket.accept()
        resolved_channels = set(channels or ["alerts"])
        if not resolved_channels:
            resolved_channels = {"alerts"}

        tenant_map = self._tenant_channel_connections.setdefault(tenant_id, {})
        for channel in resolved_channels:
            tenant_map.setdefault(channel, set()).add(websocket)
        self._socket_context[websocket] = (tenant_id, resolved_channels)

    def disconnect(self, websocket: WebSocket) -> None:
        context = self._socket_context.pop(websocket, None)
        if context is None:
            return
        tenant_id, channels = context
        tenant_map = self._tenant_channel_connections.get(tenant_id, {})
        for channel in channels:
            tenant_map.get(channel, set()).discard(websocket)
        if tenant_map and all(len(sockets) == 0 for sockets in tenant_map.values()):
            self._tenant_channel_connections.pop(tenant_id, None)

    async def broadcast(self, message: str, *, tenant_id: str, channel: str = "alerts") -> None:
        tenant_map = self._tenant_channel_connections.get(tenant_id, {})
        sockets = list(tenant_map.get(channel, set()))
        stale: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._socket_context)

    @property
    def channel_counts(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for channels in self._tenant_channel_connections.values():
            for channel, sockets in channels.items():
                summary[channel] = summary.get(channel, 0) + len(sockets)
        return summary

    @property
    def tenant_channel_counts(self) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for tenant_id, channels in self._tenant_channel_connections.items():
            result[tenant_id] = {channel: len(sockets) for channel, sockets in channels.items()}
        return result

