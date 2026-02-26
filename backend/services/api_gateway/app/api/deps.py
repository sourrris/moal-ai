from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from risk_common.security import decode_access_token

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


def get_rabbit_channel(request: Request):
    channel = getattr(request.app.state, "rabbit_channel", None)
    if channel is None:
        raise HTTPException(status_code=503, detail="Messaging not ready")
    return channel
