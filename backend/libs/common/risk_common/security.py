import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
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


def create_refresh_token(
    subject: str,
    secret_key: str,
    algorithm: str,
    expires_minutes: int,
    tenant_id: str,
    roles: list[str],
    scopes: list[str],
    session_id: str | None = None,
    token_id: str | None = None,
) -> str:
    expire = datetime.now(tz=UTC) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "roles": roles,
        "scopes": scopes,
        "typ": "refresh",
        "jti": token_id or str(uuid4()),
        "exp": expire,
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_access_token(token: str, secret_key: str, algorithm: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError:
        return None


def decode_refresh_token(token: str, secret_key: str, algorithm: str) -> dict[str, Any] | None:
    payload = decode_access_token(token, secret_key, algorithm)
    if not payload:
        return None
    if payload.get("typ") != "refresh":
        return None
    if not payload.get("tenant_id"):
        return None
    return payload


def _base64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def build_rsa_jwk(public_key_pem: str, kid: str, *, use: str = "sig", alg: str = "RS256") -> dict[str, Any]:
    key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("JWKS builder only supports RSA public keys")
    numbers = key.public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": use,
        "alg": alg,
        "n": _base64url_uint(numbers.n),
        "e": _base64url_uint(numbers.e),
    }
