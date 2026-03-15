from collections.abc import Iterable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from risk_common.schemas_v2 import AuthClaims
from risk_common.security import decode_access_token

from app.config import get_settings

security = HTTPBearer(auto_error=False)
settings = get_settings()

PLATFORM_TENANT_IDS = {"*", "all", "platform", "ops", "internal"}
PLATFORM_ROLES = {"platform_admin", "super_admin", "ops_admin"}


async def get_auth_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthClaims:
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant-scoped token required")

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


def require_any_scope(required_scopes: Iterable[str]):
    required = tuple(required_scopes)

    async def _enforce_scope(claims: AuthClaims = Depends(get_auth_claims)) -> AuthClaims:
        if not any(scope in claims.scopes for scope in required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required scope")
        return claims

    return _enforce_scope


def is_platform_operator(claims: AuthClaims) -> bool:
    if claims.tenant_id in PLATFORM_TENANT_IDS:
        return True
    return any(role in PLATFORM_ROLES for role in claims.roles)


def enforce_tenant_access(claims: AuthClaims, tenant_id: str) -> None:
    if is_platform_operator(claims):
        return
    if claims.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
