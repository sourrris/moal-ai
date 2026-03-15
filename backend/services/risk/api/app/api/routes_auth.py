import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from jose import jwt
from pydantic import BaseModel, Field, field_validator
from risk_common.schemas import TokenResponse
from risk_common.schemas_v2 import AuthClaims
from risk_common.security import (
    build_rsa_jwk,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_claims
from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.monitoring_repository import RefreshSessionRepository, UserRepository
from app.infrastructure.tenant_setup_repository import DuplicateResourceError, TenantSetupRepository

router = APIRouter(prefix="/v1/auth", tags=["auth"])
settings = get_settings()

GOOGLE_OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_OAUTH_AUTHORIZE_URL = "https://appleid.apple.com/auth/authorize"
APPLE_OAUTH_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"


class LoginRequest(BaseModel):
    username: str
    password: str
    tenant_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=256)
    organization_name: str = Field(min_length=2, max_length=255)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Username must be an email address")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(char.isupper() for char in value) or not any(char.islower() for char in value) or not any(
            char.isdigit() for char in value
        ):
            raise ValueError("Password must include upper, lower, and numeric characters")
        return value

    @field_validator("organization_name")
    @classmethod
    def normalize_organization_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Organization name is required")
        return normalized


class OAuthStatePayload(BaseModel):
    provider: str
    nonce: str


class MeResponse(BaseModel):
    username: str
    tenant_id: str
    roles: list[str]
    scopes: list[str]


def _oauth_state_secret() -> bytes:
    # OAuth state signing key is independent from JWT signing mode.
    return settings.jwt_refresh_secret_key.encode("utf-8")


def _request_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


def _cookie_kwargs() -> dict:
    domain = (settings.auth_cookie_domain or "").strip() or None
    return {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite.lower(),
        "domain": domain,
        "path": "/",
    }


def _set_auth_cookies(response: Response, *, access_token: str, refresh_token: str | None = None) -> None:
    kwargs = _cookie_kwargs()
    response.set_cookie(
        key=settings.auth_access_cookie_name,
        value=access_token,
        max_age=settings.jwt_access_token_minutes * 60,
        **kwargs,
    )
    if refresh_token is not None:
        response.set_cookie(
            key=settings.auth_refresh_cookie_name,
            value=refresh_token,
            max_age=settings.jwt_refresh_token_minutes * 60,
            **kwargs,
        )


def _clear_auth_cookies(response: Response) -> None:
    kwargs = _cookie_kwargs()
    response.delete_cookie(key=settings.auth_access_cookie_name, domain=kwargs["domain"], path=kwargs["path"])
    response.delete_cookie(key=settings.auth_refresh_cookie_name, domain=kwargs["domain"], path=kwargs["path"])


async def _issue_session_tokens(
    *,
    session: AsyncSession,
    request: Request,
    username: str,
    tenant_id: str,
    roles: list[str],
    scopes: list[str],
) -> tuple[str, str]:
    access_token = create_access_token(
        subject=username,
        secret_key=settings.jwt_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_minutes,
        tenant_id=tenant_id,
        roles=roles,
        scopes=scopes,
    )
    session_id = uuid4()
    refresh_token = create_refresh_token(
        subject=username,
        secret_key=settings.jwt_refresh_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_refresh_token_minutes,
        tenant_id=tenant_id,
        roles=roles,
        scopes=scopes,
        session_id=str(session_id),
    )
    await RefreshSessionRepository.create(
        session,
        session_id=session_id,
        username=username,
        tenant_id=tenant_id,
        refresh_token=refresh_token,
        expires_at=datetime.now(tz=UTC) + timedelta(minutes=settings.jwt_refresh_token_minutes),
        user_agent=request.headers.get("user-agent"),
        ip_address=_request_ip(request),
    )
    return access_token, refresh_token


def _create_oauth_state(provider: str) -> tuple[str, str]:
    """Create a signed opaque state token and raw nonce for OAuth flows."""
    nonce = secrets.token_urlsafe(24)
    payload = OAuthStatePayload(provider=provider, nonce=nonce).model_dump_json().encode("utf-8")
    signature = hmac.new(_oauth_state_secret(), payload, hashlib.sha256).digest()
    state = f"{base64.urlsafe_b64encode(payload).decode('utf-8')}.{base64.urlsafe_b64encode(signature).decode('utf-8')}"
    return state, nonce


def _validate_oauth_state(provider: str, state: str) -> None:
    """Validate signed OAuth state payload integrity and provider binding."""
    try:
        payload_b64, signature_b64 = state.split(".", 1)
        payload = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        provided_sig = base64.urlsafe_b64decode(signature_b64.encode("utf-8"))
    except (ValueError, base64.binascii.Error) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state") from exc

    expected_sig = hmac.new(_oauth_state_secret(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state signature mismatch")

    parsed = OAuthStatePayload.model_validate_json(payload.decode("utf-8"))
    if parsed.provider != provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth provider mismatch")


async def _verify_id_token_with_jwks(id_token: str, jwks_url: str, audience: str) -> dict:
    """Verify ID token signature and audience claim using provider JWKS endpoint."""
    try:
        header = jwt.get_unverified_header(id_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed ID token") from exc

    async with httpx.AsyncClient(timeout=10.0) as client:
        jwks_response = await client.get(jwks_url)
        jwks_response.raise_for_status()
        keys_payload = jwks_response.json().get("keys", [])

    key_payload = next((item for item in keys_payload if item.get("kid") == header.get("kid")), None)
    if key_payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to match signing key")

    try:
        claims = jwt.decode(
            id_token,
            key_payload,
            algorithms=[header.get("alg", "RS256")],
            audience=audience,
            options={"verify_at_hash": False},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid social ID token") from exc

    return claims


async def _finish_social_login(session: AsyncSession, provider: str, claims: dict, request: Request) -> RedirectResponse:
    """Issue platform token from verified social identity claims."""
    social_subject = claims.get("sub")
    email = claims.get("email")
    if not social_subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing social subject claim")

    username = email or f"{provider}:{social_subject}"
    user = await UserRepository.get_or_create_social_user(session=session, username=username)
    context = await UserRepository.resolve_tenant_context(session, user, None)
    if not context:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No tenant assignment for this user")
    access_token, refresh_token = await _issue_session_tokens(
        session=session,
        request=request,
        username=user.username,
        tenant_id=context["tenant_id"],
        roles=context["roles"],
        scopes=context["scopes"],
    )

    redirect_query = urlencode({"token": access_token, "username": user.username})
    response = RedirectResponse(url=f"{settings.frontend_base_url}/auth/callback?{redirect_query}", status_code=302)
    _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    return response


@router.get("/me", response_model=MeResponse)
async def get_me(claims: AuthClaims = Depends(get_auth_claims)) -> MeResponse:
    return MeResponse(
        username=claims.sub,
        tenant_id=claims.tenant_id,
        roles=claims.roles,
        scopes=claims.scopes,
    )


@router.get("/jwks")
async def jwks() -> dict:
    if not settings.jwt_algorithm.upper().startswith("RS"):
        return {"keys": []}
    if not settings.jwt_public_key_pem:
        raise HTTPException(status_code=500, detail="RS256 is enabled but JWT_PUBLIC_KEY_PEM is not configured")
    try:
        return {"keys": [build_rsa_jwk(settings.jwt_public_key_pem, settings.jwt_key_id, alg=settings.jwt_algorithm.upper())]}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Unable to build JWKS from configured public key: {exc}") from exc


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> TokenResponse:
    user = await UserRepository.authenticate(session, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad credentials")

    context = await UserRepository.resolve_tenant_context(session, user, payload.tenant_id)
    if not context:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No tenant assignment for this user")
    access_token, refresh_token = await _issue_session_tokens(
        session=session,
        request=request,
        username=user.username,
        tenant_id=context["tenant_id"],
        roles=context["roles"],
        scopes=context["scopes"],
    )
    _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_account(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> TokenResponse:
    try:
        account = await TenantSetupRepository.create_account(
            session,
            username=payload.username,
            password=payload.password,
            organization_name=payload.organization_name,
        )
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    access_token, refresh_token = await _issue_session_tokens(
        session=session,
        request=request,
        username=str(account["username"]),
        tenant_id=str(account["tenant_id"]),
        roles=[str(item) for item in account["roles"]],
        scopes=[str(item) for item in account["scopes"]],
    )
    _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    response.status_code = status.HTTP_201_CREATED
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> TokenResponse:
    raw_refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    if not raw_refresh_token and payload:
        raw_refresh_token = payload.refresh_token
    if not raw_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    claims = decode_refresh_token(
        raw_refresh_token,
        secret_key=settings.jwt_refresh_verification_key,
        algorithm=settings.jwt_algorithm,
    )
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    sid = claims.get("sid")
    subject = str(claims.get("sub") or "")
    tenant_id = str(claims.get("tenant_id") or "")
    roles = [str(item) for item in claims.get("roles", [])]
    scopes = [str(item) for item in claims.get("scopes", [])]
    if not sid or not subject or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token claims")

    session_row = await RefreshSessionRepository.get_active_by_session_id(session, session_id=str(sid))
    if not session_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown refresh session")
    if str(session_row.get("username") or "") != subject or str(session_row.get("tenant_id") or "") != tenant_id:
        await RefreshSessionRepository.revoke(session, session_id=str(sid))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session mismatch")
    if datetime.now(tz=UTC) >= session_row["expires_at"]:
        await RefreshSessionRepository.revoke(session, session_id=str(sid))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session expired")
    if str(session_row.get("refresh_token_hash") or "") != RefreshSessionRepository.hash_token(raw_refresh_token):
        await RefreshSessionRepository.revoke(session, session_id=str(sid))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token replay detected")

    access_token = create_access_token(
        subject=subject,
        secret_key=settings.jwt_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_minutes,
        tenant_id=tenant_id,
        roles=roles,
        scopes=scopes,
    )
    next_refresh_token = create_refresh_token(
        subject=subject,
        secret_key=settings.jwt_refresh_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_refresh_token_minutes,
        tenant_id=tenant_id,
        roles=roles,
        scopes=scopes,
        session_id=str(sid),
    )
    rotated = await RefreshSessionRepository.rotate(
        session,
        session_id=str(sid),
        current_refresh_token=raw_refresh_token,
        next_refresh_token=next_refresh_token,
        expires_at=datetime.now(tz=UTC) + timedelta(minutes=settings.jwt_refresh_token_minutes),
        user_agent=request.headers.get("user-agent"),
        ip_address=_request_ip(request),
    )
    if not rotated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session rotation failed")

    _set_auth_cookies(response, access_token=access_token, refresh_token=next_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> dict:
    raw_refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    if not raw_refresh_token and payload:
        raw_refresh_token = payload.refresh_token
    if raw_refresh_token:
        claims = decode_refresh_token(
            raw_refresh_token,
            secret_key=settings.jwt_refresh_verification_key,
            algorithm=settings.jwt_algorithm,
        )
        sid = str(claims.get("sid") or "") if claims else ""
        if sid:
            await RefreshSessionRepository.revoke(session, session_id=sid)
    _clear_auth_cookies(response)
    return {"status": "logged_out"}


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    """Redirect user-agent to Google OAuth authorization endpoint."""
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google OAuth is not configured")

    state, nonce = _create_oauth_state("google")
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    return RedirectResponse(url=f"{GOOGLE_OAUTH_AUTHORIZE_URL}?{urlencode(params)}", status_code=302)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> RedirectResponse:
    """Handle Google OAuth callback and issue internal access token."""
    _validate_oauth_state("google", state)

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            GOOGLE_OAUTH_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_response.raise_for_status()

    token_payload = token_response.json()
    id_token = token_payload.get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google did not return ID token")

    claims = await _verify_id_token_with_jwks(
        id_token=id_token,
        jwks_url=GOOGLE_JWKS_URL,
        audience=settings.google_oauth_client_id,
    )

    return await _finish_social_login(session=session, provider="google", claims=claims, request=request)


@router.get("/apple/login")
async def apple_login() -> RedirectResponse:
    """Redirect user-agent to Apple OAuth authorization endpoint."""
    if not settings.apple_oauth_client_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Apple OAuth is not configured")

    state, nonce = _create_oauth_state("apple")
    params = {
        "client_id": settings.apple_oauth_client_id,
        "redirect_uri": settings.apple_oauth_redirect_uri,
        "response_type": "code",
        "response_mode": "form_post",
        "scope": "name email",
        "state": state,
        "nonce": nonce,
    }
    return RedirectResponse(url=f"{APPLE_OAUTH_AUTHORIZE_URL}?{urlencode(params)}", status_code=302)


@router.api_route("/apple/callback", methods=["GET", "POST"])
async def apple_callback(
    request: Request,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle Apple OAuth callback and issue internal access token."""
    callback_data: dict[str, str] = {}
    if request.method == "POST":
        form = await request.form()
        callback_data = {key: str(value) for key, value in form.items()}

    code_value = callback_data.get("code") or code
    state_value = callback_data.get("state") or state

    if not code_value or not state_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apple callback missing required fields")

    _validate_oauth_state("apple", state_value)

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            APPLE_OAUTH_TOKEN_URL,
            data={
                "code": code_value,
                "client_id": settings.apple_oauth_client_id,
                "client_secret": settings.apple_oauth_client_secret,
                "redirect_uri": settings.apple_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_response.raise_for_status()

    token_payload = token_response.json()
    id_token = token_payload.get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Apple did not return ID token")

    claims = await _verify_id_token_with_jwks(
        id_token=id_token,
        jwks_url=APPLE_JWKS_URL,
        audience=settings.apple_oauth_client_id,
    )

    return await _finish_social_login(session=session, provider="apple", claims=claims, request=request)
