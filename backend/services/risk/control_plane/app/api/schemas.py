from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ALERT_CHANNEL = Literal["webhook", "email", "slack"]


class TenantCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=2, max_length=120)
    display_name: str = Field(min_length=2, max_length=255)
    status: str = Field(default="active", min_length=2, max_length=32)
    tier: str = Field(default="standard", min_length=2, max_length=32)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=255)
    status: str | None = Field(default=None, min_length=2, max_length=32)
    tier: str | None = Field(default=None, min_length=2, max_length=32)
    metadata_json: dict[str, Any] | None = None


class TenantAdminAssignRequest(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    role_name: str = Field(default="admin", min_length=2, max_length=64)


class TenantSummary(BaseModel):
    tenant_id: str
    display_name: str
    status: str
    tier: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None


class RuleOverridesDTO(BaseModel):
    high_amount_threshold: float | None = None
    high_amount_weight: float | None = None
    sanctions_weight: float | None = None
    pep_weight: float | None = None
    proxy_ip_weight: float | None = None
    bin_mismatch_weight: float | None = None
    jurisdiction_threshold: float | None = None
    jurisdiction_weight: float | None = None
    cross_border_weight: float | None = None


class TenantConfigurationDTO(BaseModel):
    tenant_id: str
    anomaly_threshold: float | None = None
    enabled_connectors: list[str] = Field(default_factory=list)
    model_version: str | None = None
    rule_overrides_json: dict[str, Any] = Field(default_factory=dict)
    version: int
    updated_at: datetime


class TenantConfigurationUpdateRequest(BaseModel):
    anomaly_threshold: float | None = None
    enabled_connectors: list[str] | None = None
    model_version: str | None = None
    rule_overrides_json: dict[str, Any] | None = None
    expected_version: int | None = None


class ConnectorCatalogItem(BaseModel):
    source_name: str
    source_type: str
    enabled: bool
    cadence_seconds: int
    freshness_slo_seconds: int | None = None
    latest_status: str | None = None
    latest_run_at: datetime | None = None


class TenantConnectorPolicyResponse(BaseModel):
    tenant_id: str
    enabled_connectors: list[str] = Field(default_factory=list)
    all_sources: list[ConnectorCatalogItem] = Field(default_factory=list)


class TenantConnectorPolicyUpdateRequest(BaseModel):
    enabled_connectors: list[str] = Field(default_factory=list)
    expected_version: int | None = None


class ModelActivateRequest(BaseModel):
    model_name: str = Field(min_length=2, max_length=120)
    model_version: str = Field(min_length=2, max_length=64)


class ModelPolicyUpdateRequest(BaseModel):
    model_version: str | None = Field(default=None, min_length=2, max_length=64)
    expected_version: int | None = None


class TestDatasetUploadRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    source_type: str = Field(default="json", min_length=2, max_length=32)
    events: list[dict[str, Any]] = Field(default_factory=list)


class TestDatasetSummary(BaseModel):
    dataset_id: UUID
    tenant_id: str
    name: str
    source_type: str
    row_count: int
    uploaded_by: str | None = None
    created_at: datetime


class TestRunCreateRequest(BaseModel):
    dataset_id: UUID | None = None
    events: list[dict[str, Any]] | None = None


class TestRunSummary(BaseModel):
    run_id: UUID
    tenant_id: str
    dataset_id: UUID | None = None
    status: str
    created_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TestRunResultItem(BaseModel):
    event_id: UUID | None = None
    ingest_status: str | None = None
    queued: bool | None = None
    decision_found: bool
    risk_level: str | None = None
    risk_score: float | None = None
    alert_found: bool
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AlertDestinationCreateRequest(BaseModel):
    channel: ALERT_CHANNEL
    name: str = Field(min_length=2, max_length=255)
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class AlertDestinationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class AlertDestinationDTO(BaseModel):
    destination_id: UUID
    tenant_id: str
    channel: ALERT_CHANNEL
    name: str
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    verification_status: str
    last_tested_at: datetime | None = None
    updated_at: datetime


class AlertRoutingPolicyDTO(BaseModel):
    tenant_id: str
    policy_json: dict[str, Any] = Field(default_factory=dict)
    updated_by: str | None = None
    updated_at: datetime


class AlertRoutingPolicyUpdateRequest(BaseModel):
    policy_json: dict[str, Any] = Field(default_factory=dict)


class AlertRoutingTestRequest(BaseModel):
    severity: str = Field(default="critical", min_length=2, max_length=32)
    payload: dict[str, Any] = Field(default_factory=dict)


class DeliveryResult(BaseModel):
    destination_id: UUID
    channel: ALERT_CHANNEL
    status: str
    attempt_no: int
    error_message: str | None = None


class ReconciliationSummaryDTO(BaseModel):
    tenant_id: str
    from_ts: datetime
    to_ts: datetime
    ingested_events: int
    processed_decisions: int
    raised_alerts: int
    delivered_alerts: int
    failed_deliveries: int
    mismatch_count: int


class DeliveryLogItem(BaseModel):
    delivery_id: UUID
    tenant_id: str
    destination_id: UUID | None = None
    channel: ALERT_CHANNEL
    alert_key: str
    event_id: UUID | None = None
    status: str
    attempt_no: int
    response_code: int | None = None
    error_message: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    is_test: bool = False
    attempted_at: datetime
    delivered_at: datetime | None = None


class ConfigAuditItem(BaseModel):
    id: int
    tenant_id: str | None = None
    actor: str
    action: str
    resource_type: str
    resource_id: str | None = None
    before_json: dict[str, Any] = Field(default_factory=dict)
    after_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
