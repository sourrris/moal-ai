"""Backward-compat re-exports. New code should import from moal_common.schemas."""

from pydantic import BaseModel, Field


class AuthClaims(BaseModel):
    sub: str
    tenant_id: str = "default"
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
