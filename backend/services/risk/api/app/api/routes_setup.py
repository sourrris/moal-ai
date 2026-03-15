from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from risk_common.schemas_v2 import AuthClaims
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_claims
from app.infrastructure.db import get_db_session
from app.infrastructure.tenant_setup_repository import (
    DomainRepository,
    DuplicateResourceError,
    NotFoundError,
    TenantKeyRepository,
)

router = APIRouter(prefix="/v1", tags=["tenant-setup"])


class DomainCreateRequest(BaseModel):
    hostname: str = Field(min_length=4, max_length=255)


class DomainResponse(BaseModel):
    domain_id: UUID
    tenant_id: str
    hostname: str
    created_by: str | None = None
    created_at: datetime


class DomainListResponse(BaseModel):
    items: list[DomainResponse]


class ApiKeyResponse(BaseModel):
    key_id: UUID
    tenant_id: str
    name: str
    key_prefix: str
    active: bool
    scopes: list[str] = Field(default_factory=list)
    domain_id: UUID | None = None
    domain_hostname: str | None = None
    created_by: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyResponse]


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    domain_id: UUID


class ApiKeyCreateResponse(ApiKeyResponse):
    token: str


def require_admin_claims(claims: AuthClaims = Depends(get_auth_claims)) -> AuthClaims:
    if "admin" not in claims.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return claims


@router.get("/domains", response_model=DomainListResponse)
async def list_domains(
    claims: AuthClaims = Depends(require_admin_claims),
    session: AsyncSession = Depends(get_db_session),
) -> DomainListResponse:
    return DomainListResponse(items=await DomainRepository.list_domains(session, tenant_id=claims.tenant_id))


@router.post("/domains", response_model=DomainResponse, status_code=status.HTTP_201_CREATED)
async def create_domain(
    payload: DomainCreateRequest,
    claims: AuthClaims = Depends(require_admin_claims),
    session: AsyncSession = Depends(get_db_session),
) -> DomainResponse:
    try:
        domain = await DomainRepository.create_domain(
            session,
            tenant_id=claims.tenant_id,
            hostname=payload.hostname,
            created_by=claims.sub,
        )
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return DomainResponse.model_validate(domain)


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    claims: AuthClaims = Depends(require_admin_claims),
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyListResponse:
    return ApiKeyListResponse(items=await TenantKeyRepository.list_keys(session, tenant_id=claims.tenant_id))


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    claims: AuthClaims = Depends(require_admin_claims),
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyCreateResponse:
    try:
        created = await TenantKeyRepository.create_key(
            session,
            tenant_id=claims.tenant_id,
            name=payload.name,
            domain_id=payload.domain_id,
            created_by=claims.sub,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ApiKeyCreateResponse.model_validate(created)


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: UUID,
    claims: AuthClaims = Depends(require_admin_claims),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    revoked = await TenantKeyRepository.revoke_key(session, tenant_id=claims.tenant_id, key_id=key_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"status": "revoked"}
