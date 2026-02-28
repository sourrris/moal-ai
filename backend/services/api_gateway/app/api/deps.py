from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from risk_common.security import decode_access_token
from risk_common.schemas_v2 import AuthClaims

security = HTTPBearer()
settings = get_settings()


async def get_current_subject(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    payload = decode_access_token(
        credentials.credentials,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return str(payload["sub"])


async def get_auth_claims(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthClaims:
    payload = decode_access_token(
        credentials.credentials,
        secret_key=settings.jwt_secret_key,
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
