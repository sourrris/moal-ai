"""Unit tests for tenant-scoped websocket routing."""

import asyncio
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "services" / "risk" / "notification" / "app" / "domain" / "connection_manager.py"
SPEC = importlib.util.spec_from_file_location("notification_connection_manager", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ConnectionManager = MODULE.ConnectionManager


class DummySocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def accept(self) -> None:
        return None

    async def send_text(self, message: str) -> None:
        self.messages.append(message)


def test_tenant_scoped_broadcast_only_reaches_target_tenant() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        tenant_alpha_socket = DummySocket()
        tenant_beta_socket = DummySocket()

        await manager.connect(tenant_alpha_socket, tenant_id="tenant-alpha", channels=["alerts"])
        await manager.connect(tenant_beta_socket, tenant_id="tenant-beta", channels=["alerts"])

        await manager.broadcast('{"tenant_id":"tenant-alpha"}', tenant_id="tenant-alpha", channel="alerts")

        assert tenant_alpha_socket.messages == ['{"tenant_id":"tenant-alpha"}']
        assert tenant_beta_socket.messages == []

    asyncio.run(scenario())
