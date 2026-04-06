from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from moal_common.schemas import TokenResponse
from moal_common.schemas_v2 import AuthClaims
from moal_common.security import create_access_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_claims
from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.monitoring_repository import UserRepository

router = APIRouter(prefix="/v1/auth", tags=["auth"])
settings = get_settings()


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(char.isupper() for char in value) or not any(char.islower() for char in value) or not any(
            char.isdigit() for char in value
        ):
            raise ValueError("Password must include upper, lower, and numeric characters")
        return value


class MeResponse(BaseModel):
    username: str
    roles: list[str]
    scopes: list[str]


@router.get("/me", response_model=MeResponse)
async def get_me(claims: AuthClaims = Depends(get_auth_claims)) -> MeResponse:
    return MeResponse(
        username=claims.sub,
        roles=claims.roles,
        scopes=claims.scopes,
    )


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> TokenResponse:
    user = await UserRepository.authenticate(session, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad credentials")

    access_token = create_access_token(
        subject=user.username,
        secret_key=settings.jwt_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_minutes,
        tenant_id="default",
        roles=["admin"],
        scopes=["events:read", "events:write", "alerts:read", "alerts:write", "models:read", "models:write"],
    )
    return TokenResponse(access_token=access_token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_account(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> TokenResponse:
    existing = await UserRepository.get_by_username(session, payload.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    user = await UserRepository.create_user(session, payload.username, payload.password)
    access_token = create_access_token(
        subject=user.username,
        secret_key=settings.jwt_signing_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_minutes,
        tenant_id="default",
        roles=["admin"],
        scopes=["events:read", "events:write", "alerts:read", "alerts:write", "models:read", "models:write"],
    )
    return TokenResponse(access_token=access_token)
