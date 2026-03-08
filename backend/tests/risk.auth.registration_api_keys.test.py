"""Route-level tests for registration, setup, and API-key auth flows."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))
sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "risk" / "api"))

from app.api import deps, routes_auth, routes_setup
from app.infrastructure.db import get_db_session
from app.infrastructure.tenant_setup_repository import DuplicateResourceError
from risk_common.schemas_v2 import AuthClaims


def _configure_auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_auth.settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(routes_auth.settings, "jwt_secret_key", "test-signing-secret")
    monkeypatch.setattr(routes_auth.settings, "jwt_refresh_secret_key", "test-refresh-secret")
    monkeypatch.setattr(routes_auth.settings, "jwt_access_token_minutes", 10)
    monkeypatch.setattr(routes_auth.settings, "jwt_refresh_token_minutes", 60)
    monkeypatch.setattr(routes_auth.settings, "auth_access_cookie_name", "aegis_access_token")
    monkeypatch.setattr(routes_auth.settings, "auth_refresh_cookie_name", "aegis_refresh_token")
    monkeypatch.setattr(routes_auth.settings, "auth_cookie_secure", False)
    monkeypatch.setattr(routes_auth.settings, "auth_cookie_domain", None)
    monkeypatch.setattr(routes_auth.settings, "auth_cookie_samesite", "lax")


def _test_app(session_obj: object, *routers) -> FastAPI:
    app = FastAPI()
    for router in routers:
        app.include_router(router)

    async def _override_db():
        yield session_obj

    app.dependency_overrides[get_db_session] = _override_db
    return app


@pytest.mark.asyncio
async def test_register_route_bootstraps_account_and_sets_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_auth_settings(monkeypatch)
    create_calls: dict[str, object] = {}

    async def fake_create_account(_session, *, username, password, organization_name):
        create_calls.update(
            {
                "username": username,
                "password": password,
                "organization_name": organization_name,
            }
        )
        return {
            "username": username,
            "tenant_id": "test-org",
            "roles": ["admin"],
            "scopes": ["events:write", "events:read"],
        }

    async def fake_refresh_create(
        _session,
        *,
        session_id,
        username,
        tenant_id,
        refresh_token,
        expires_at,
        user_agent=None,
        ip_address=None,
    ):
        _ = (session_id, username, tenant_id, refresh_token, expires_at, user_agent, ip_address)

    monkeypatch.setattr(routes_auth.TenantSetupRepository, "create_account", fake_create_account)
    monkeypatch.setattr(routes_auth.RefreshSessionRepository, "create", fake_refresh_create)

    app = _test_app(SimpleNamespace(), routes_auth.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/auth/register",
            json={
                "username": "Test@Example.com",
                "password": "TestPass123",
                "organization_name": "Test Org",
            },
        )

    assert response.status_code == 201
    assert response.json()["access_token"]
    assert response.cookies.get("aegis_access_token")
    assert response.cookies.get("aegis_refresh_token")
    assert create_calls == {
        "username": "test@example.com",
        "password": "TestPass123",
        "organization_name": "Test Org",
    }


@pytest.mark.asyncio
async def test_register_route_uses_configured_cookie_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_auth_settings(monkeypatch)
    monkeypatch.setattr(routes_auth.settings, "auth_cookie_domain", "localhost")

    async def fake_create_account(_session, *, username, password, organization_name):
        _ = (password, organization_name)
        return {
            "username": username,
            "tenant_id": "test-org",
            "roles": ["admin"],
            "scopes": ["events:write", "events:read"],
        }

    async def fake_refresh_create(
        _session,
        *,
        session_id,
        username,
        tenant_id,
        refresh_token,
        expires_at,
        user_agent=None,
        ip_address=None,
    ):
        _ = (session_id, username, tenant_id, refresh_token, expires_at, user_agent, ip_address)

    monkeypatch.setattr(routes_auth.TenantSetupRepository, "create_account", fake_create_account)
    monkeypatch.setattr(routes_auth.RefreshSessionRepository, "create", fake_refresh_create)

    app = _test_app(SimpleNamespace(), routes_auth.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/auth/register",
            json={
                "username": "domain@example.com",
                "password": "TestPass123",
                "organization_name": "Domain Org",
            },
        )

    assert response.status_code == 201
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("Domain=localhost" in header for header in set_cookie_headers)


@pytest.mark.asyncio
async def test_require_scope_accepts_valid_x_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_authenticate(_session, raw_key):
        assert raw_key == "test-api-key-scope-check-value"
        return {
            "tenant_id": "tenant-gamma",
            "scopes": ["events:write"],
            "api_key_id": "6bc6483e-42ba-44dd-9db7-5b265c657ab5",
            "key_prefix": "test-key-prefix",
            "domain_id": "8472979c-f10a-4827-8df2-a6ec5ea08045",
            "domain_hostname": "app.example.com",
        }

    monkeypatch.setattr(deps.TenantKeyRepository, "authenticate_api_key", fake_authenticate)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/secure",
            "headers": [(b"x-api-key", b"test-api-key-scope-check-value")],
        }
    )

    claims = await deps.get_auth_claims(request=request, credentials=None, session=SimpleNamespace())
    enforced_claims = await deps.require_scope("events:write")(claims)
    payload = enforced_claims.model_dump()
    assert payload["tenant_id"] == "tenant-gamma"
    assert payload["domain_hostname"] == "app.example.com"
    assert payload["sub"] == "api-key:test-key-prefix"


@pytest.mark.asyncio
async def test_create_domain_route_returns_conflict_for_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_domain(_session, *, tenant_id, hostname, created_by):
        _ = (tenant_id, hostname, created_by)
        raise DuplicateResourceError("This domain is already configured for your organization")

    monkeypatch.setattr(routes_setup.DomainRepository, "create_domain", fake_create_domain)

    app = _test_app(SimpleNamespace(), routes_setup.router)
    app.dependency_overrides[routes_setup.require_admin_claims] = lambda: AuthClaims(
        sub="admin@example.com",
        tenant_id="tenant-gamma",
        roles=["admin"],
        scopes=["events:write"],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/domains", json={"hostname": "app.example.com"})

    assert response.status_code == 409
    assert response.json()["detail"] == "This domain is already configured for your organization"
