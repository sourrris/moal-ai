from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from risk_common.schemas_v2 import RefreshTokenRequest, TokenPairResponse
from risk_common.security import create_access_token, create_refresh_token, decode_refresh_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.monitoring_repository import UserRepository

router = APIRouter(prefix="/v2/auth", tags=["auth-v2"])
settings = get_settings()


class LoginRequestV2(BaseModel):
    username: str
    password: str
    tenant_id: str | None = None


@router.post("/token", response_model=TokenPairResponse)
async def issue_token_v2(
    payload: LoginRequestV2,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    user = await UserRepository.authenticate(session, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad credentials")

    context = await UserRepository.resolve_tenant_context(session, user, payload.tenant_id)

    access_token = create_access_token(
        subject=user.username,
        secret_key=settings.jwt_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_minutes,
        tenant_id=context["tenant_id"],
        roles=context["roles"],
        scopes=context["scopes"],
    )
    refresh_token = create_refresh_token(
        subject=user.username,
        secret_key=settings.jwt_refresh_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_refresh_token_minutes,
        tenant_id=context["tenant_id"],
        roles=context["roles"],
        scopes=context["scopes"],
    )

    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_minutes * 60,
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_token_v2(payload: RefreshTokenRequest) -> TokenPairResponse:
    claims = decode_refresh_token(
        payload.refresh_token,
        secret_key=settings.jwt_refresh_verification_key,
        algorithm=settings.jwt_algorithm,
    )
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    subject = str(claims.get("sub", ""))
    tenant_id = str(claims.get("tenant_id", ""))
    roles = [str(item) for item in claims.get("roles", [])]
    scopes = [str(item) for item in claims.get("scopes", [])]
    if not subject or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    access_token = create_access_token(
        subject=subject,
        secret_key=settings.jwt_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_minutes,
        tenant_id=tenant_id,
        roles=roles,
        scopes=scopes,
    )
    refresh_token = create_refresh_token(
        subject=subject,
        secret_key=settings.jwt_refresh_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_refresh_token_minutes,
        tenant_id=tenant_id,
        roles=roles,
        scopes=scopes,
    )

    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_minutes * 60,
    )
