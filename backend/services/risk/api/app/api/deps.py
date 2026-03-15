from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from risk_common.schemas_v2 import AuthClaims
from risk_common.security import decode_access_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.tenant_setup_repository import TenantKeyRepository

security = HTTPBearer(auto_error=False)
settings = get_settings()


async def get_current_subject(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    raw_token = credentials.credentials if credentials else request.cookies.get(settings.auth_access_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    payload = decode_access_token(
        raw_token,
        secret_key=settings.jwt_verification_key,
        algorithm=settings.jwt_algorithm,
    )
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return str(payload["sub"])


async def get_auth_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> AuthClaims:
    raw_api_key = request.headers.get("x-api-key")
    if raw_api_key:
        api_key_claims = await TenantKeyRepository.authenticate_api_key(session, raw_api_key)
        if not api_key_claims:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return AuthClaims(
            sub=f"api-key:{api_key_claims['key_prefix']}",
            tenant_id=str(api_key_claims["tenant_id"]),
            roles=["api_key"],
            scopes=[str(item) for item in api_key_claims.get("scopes", [])],
            api_key_id=str(api_key_claims["api_key_id"]),
            key_prefix=str(api_key_claims["key_prefix"]),
            domain_id=str(api_key_claims["domain_id"]) if api_key_claims.get("domain_id") else None,
            domain_hostname=str(api_key_claims["domain_hostname"]) if api_key_claims.get("domain_hostname") else None,
        )

    raw_token = credentials.credentials if credentials else request.cookies.get(settings.auth_access_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    payload = decode_access_token(
        raw_token,
        secret_key=settings.jwt_verification_key,
        algorithm=settings.jwt_algorithm,
    )
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant-scoped token required for v2 endpoints",
        )

    roles = payload.get("roles") if isinstance(payload.get("roles"), list) else []
    scopes = payload.get("scopes") if isinstance(payload.get("scopes"), list) else []
    return AuthClaims(
        sub=str(payload["sub"]),
        tenant_id=str(tenant_id),
        roles=[str(item) for item in roles],
        scopes=[str(item) for item in scopes],
    )


def require_scope(required_scope: str):
    async def _enforce_scope(claims: AuthClaims = Depends(get_auth_claims)) -> AuthClaims:
        if required_scope not in claims.scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required scope")
        return claims

    return _enforce_scope


def get_rabbit_channel(request: Request):
    channel = getattr(request.app.state, "rabbit_channel", None)
    if channel is None:
        raise HTTPException(status_code=503, detail="Messaging not ready")
    return channel
