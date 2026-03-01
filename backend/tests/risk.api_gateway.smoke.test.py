"""Smoke tests for API gateway health endpoints."""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))
sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "risk" / "api"))

from app.main import health_live


@pytest.mark.asyncio
async def test_health_live_handler_returns_ok_payload() -> None:
    """Verify the health handler returns a healthy status payload."""
    payload = await health_live()

    assert payload.status == "ok"
    assert payload.service == "api-gateway"
