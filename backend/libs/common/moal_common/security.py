from datetime import UTC, datetime, timedelta
from typing import Any
from jose import JWTError, jwt


def create_access_token(
    subject: str,
    secret_key: str,
    algorithm: str,
    expires_minutes: int,
    tenant_id: str | None = None,
    roles: list[str] | None = None,
    scopes: list[str] | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expire = datetime.now(tz=UTC) + timedelta(minutes=expires_minutes)
    payload = {"sub": subject, "exp": expire}
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if roles is not None:
        payload["roles"] = roles
    if scopes is not None:
        payload["scopes"] = scopes
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_access_token(token: str, secret_key: str, algorithm: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError:
        return None
