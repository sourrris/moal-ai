"""Unit tests for v2 JWT claims and refresh token flows."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))

from risk_common.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


def test_access_token_includes_tenant_roles_and_scopes() -> None:
    token = create_access_token(
        subject="alice",
        secret_key="secret",
        algorithm="HS256",
        expires_minutes=30,
        tenant_id="tenant-alpha",
        roles=["analyst"],
        scopes=["events:read", "alerts:read"],
    )

    payload = decode_access_token(token, secret_key="secret", algorithm="HS256")
    assert payload is not None
    assert payload["sub"] == "alice"
    assert payload["tenant_id"] == "tenant-alpha"
    assert payload["roles"] == ["analyst"]
    assert payload["scopes"] == ["events:read", "alerts:read"]


def test_refresh_token_round_trip_and_type_enforcement() -> None:
    refresh = create_refresh_token(
        subject="bob",
        secret_key="refresh-secret",
        algorithm="HS256",
        expires_minutes=120,
        tenant_id="tenant-beta",
        roles=["admin"],
        scopes=["events:write"],
    )

    payload = decode_refresh_token(refresh, secret_key="refresh-secret", algorithm="HS256")
    assert payload is not None
    assert payload["typ"] == "refresh"
    assert payload["tenant_id"] == "tenant-beta"

    access = create_access_token(
        subject="bob",
        secret_key="refresh-secret",
        algorithm="HS256",
        expires_minutes=30,
        tenant_id="tenant-beta",
        roles=["admin"],
        scopes=["events:write"],
    )
    assert decode_refresh_token(access, secret_key="refresh-secret", algorithm="HS256") is None
