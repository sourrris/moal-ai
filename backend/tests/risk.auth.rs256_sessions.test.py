"""Auth tests for RS256 JWKS and cookie refresh/logout flows."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))
sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "risk" / "api"))

from app.api import routes_auth
from app.infrastructure.db import get_db_session


@dataclass
class FakeUser:
    username: str
    role: str = "admin"


def _make_rsa_keys() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _test_app(session_obj: object) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_auth.router)

    async def _override_db():
        yield session_obj

    app.dependency_overrides[get_db_session] = _override_db
    return app


@pytest.mark.asyncio
async def test_jwks_endpoint_exposes_rsa_key(monkeypatch: pytest.MonkeyPatch) -> None:
    private_pem, public_pem = _make_rsa_keys()
    monkeypatch.setattr(routes_auth.settings, "jwt_algorithm", "RS256")
    monkeypatch.setattr(routes_auth.settings, "jwt_private_key_pem", private_pem)
    monkeypatch.setattr(routes_auth.settings, "jwt_public_key_pem", public_pem)
    monkeypatch.setattr(routes_auth.settings, "jwt_key_id", "test-kid-1")

    app = _test_app(SimpleNamespace())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/auth/jwks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["keys"][0]["kid"] == "test-kid-1"
    assert payload["keys"][0]["kty"] == "RSA"
    assert payload["keys"][0]["alg"] == "RS256"


@pytest.mark.asyncio
async def test_cookie_refresh_and_logout_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    private_pem, public_pem = _make_rsa_keys()
    monkeypatch.setattr(routes_auth.settings, "jwt_algorithm", "RS256")
    monkeypatch.setattr(routes_auth.settings, "jwt_private_key_pem", private_pem)
    monkeypatch.setattr(routes_auth.settings, "jwt_public_key_pem", public_pem)
    monkeypatch.setattr(routes_auth.settings, "jwt_access_token_minutes", 10)
    monkeypatch.setattr(routes_auth.settings, "jwt_refresh_token_minutes", 60)
    monkeypatch.setattr(routes_auth.settings, "auth_access_cookie_name", "aegis_access_token")
    monkeypatch.setattr(routes_auth.settings, "auth_refresh_cookie_name", "aegis_refresh_token")
    monkeypatch.setattr(routes_auth.settings, "auth_cookie_secure", False)
    monkeypatch.setattr(routes_auth.settings, "auth_cookie_domain", None)
    monkeypatch.setattr(routes_auth.settings, "auth_cookie_samesite", "lax")

    sessions: dict[str, dict] = {}

    async def fake_authenticate(_session, username, password):
        if username == "admin" and password == "admin123":
            return FakeUser(username="admin")
        return None

    async def fake_context(_session, user, requested_tenant_id=None):
        _ = requested_tenant_id
        return {"tenant_id": "tenant-alpha", "roles": [user.role], "scopes": ["events:read", "models:read", "models:write"]}

    async def fake_create(_session, *, session_id, username, tenant_id, refresh_token, expires_at, user_agent=None, ip_address=None):
        sessions[str(session_id)] = {
            "session_id": str(session_id),
            "username": username,
            "tenant_id": tenant_id,
            "refresh_token_hash": routes_auth.RefreshSessionRepository.hash_token(refresh_token),
            "expires_at": expires_at,
            "revoked_at": None,
            "user_agent": user_agent,
            "ip_address": ip_address,
        }

    async def fake_get_active(_session, *, session_id):
        row = sessions.get(session_id)
        if not row or row.get("revoked_at") is not None:
            return None
        return row

    async def fake_rotate(
        _session,
        *,
        session_id,
        current_refresh_token,
        next_refresh_token,
        expires_at,
        user_agent=None,
        ip_address=None,
    ):
        row = sessions.get(session_id)
        if not row or row.get("revoked_at") is not None:
            return False
        if row["refresh_token_hash"] != routes_auth.RefreshSessionRepository.hash_token(current_refresh_token):
            return False
        row["refresh_token_hash"] = routes_auth.RefreshSessionRepository.hash_token(next_refresh_token)
        row["expires_at"] = expires_at
        row["user_agent"] = user_agent
        row["ip_address"] = ip_address
        return True

    async def fake_revoke(_session, *, session_id):
        row = sessions.get(session_id)
        if row:
            row["revoked_at"] = datetime.now(tz=UTC)

    monkeypatch.setattr(routes_auth.UserRepository, "authenticate", fake_authenticate)
    monkeypatch.setattr(routes_auth.UserRepository, "resolve_tenant_context", fake_context)
    monkeypatch.setattr(routes_auth.RefreshSessionRepository, "create", fake_create)
    monkeypatch.setattr(routes_auth.RefreshSessionRepository, "get_active_by_session_id", fake_get_active)
    monkeypatch.setattr(routes_auth.RefreshSessionRepository, "rotate", fake_rotate)
    monkeypatch.setattr(routes_auth.RefreshSessionRepository, "revoke", fake_revoke)

    app = _test_app(SimpleNamespace())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login_response = await client.post("/v1/auth/token", json={"username": "admin", "password": "admin123"})
        assert login_response.status_code == 200
        assert login_response.cookies.get("aegis_access_token")
        assert login_response.cookies.get("aegis_refresh_token")

        refresh_response = await client.post("/v1/auth/refresh")
        assert refresh_response.status_code == 200
        assert refresh_response.json()["access_token"]
        assert client.cookies.get("aegis_refresh_token")

        logout_response = await client.post("/v1/auth/logout")
        assert logout_response.status_code == 200
        assert logout_response.json()["status"] == "logged_out"

    assert any(row.get("revoked_at") is not None for row in sessions.values())
