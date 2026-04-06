from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, IPvAnyAddress, field_validator


class AuthClaims(BaseModel):
    sub: str
    tenant_id: str
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    api_key_id: str | None = None
    key_prefix: str | None = None
    domain_id: str | None = None
    domain_hostname: str | None = None


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TransactionPayload(BaseModel):
    transaction_id: str | None = None
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=12)
    source_ip: IPvAnyAddress | None = None
    source_country: str | None = Field(default=None, min_length=2, max_length=8)
    destination_country: str | None = Field(default=None, min_length=2, max_length=8)
    card_bin: str | None = Field(default=None, min_length=6, max_length=12)
    card_last4: str | None = Field(default=None, min_length=4, max_length=4)
    merchant_id: str | None = None
    merchant_category: str | None = None
    user_email_hash: str | None = Field(default=None, min_length=16, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class RiskEventIngestRequest(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    idempotency_key: str = Field(min_length=8, max_length=128)
    source: str = Field(min_length=2, max_length=120)
    event_type: str = Field(default="transaction", min_length=2, max_length=120)
    transaction: TransactionPayload
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    features: list[float] | None = None


class RiskEventBatchIngestRequest(BaseModel):
    events: list[RiskEventIngestRequest] = Field(min_length=1, max_length=500)


class RiskEventV2(BaseModel):
    event_id: UUID
    idempotency_key: str
    tenant_id: str
    source: str
    event_type: str
    transaction: TransactionPayload
    occurred_at: datetime
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    submitted_by: str
    features: list[float] | None = None


class EventIngestResult(BaseModel):
    event_id: UUID
    status: str
    queued: bool


class BatchIngestResult(BaseModel):
    accepted: int
    duplicates: int
    failed: int
    results: list[EventIngestResult]


class RiskDecisionV2(BaseModel):
    decision_id: UUID
    event_id: UUID
    tenant_id: str
    risk_score: float
    risk_level: str
    reasons: list[str] = Field(default_factory=list)
    rule_hits: list[str] = Field(default_factory=list)
    model_name: str
    model_version: str
    ml_anomaly_score: float | None = None
    ml_threshold: float | None = None
    decision_latency_ms: int | None = None
    feature_vector: list[float] = Field(default_factory=list)
    decision_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AlertV2(BaseModel):
    alert_id: UUID
    event_id: UUID
    tenant_id: str
    decision_id: UUID | None = None
    state: str
    severity: str
    risk_score: float
    reasons: list[str] = Field(default_factory=list)
    opened_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class AlertLifecycleUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class DataSourceRunSummary(BaseModel):
    run_id: UUID
    source_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    fetched_records: int
    upserted_records: int
    checksum: str | None = None
    cursor_state: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    error_summary: dict[str, Any] = Field(default_factory=dict)


class DataSourceStatus(BaseModel):
    source_name: str
    enabled: bool = True
    cadence_seconds: int | None = None
    freshness_slo_seconds: int | None = None
    latest_status: str | None
    latest_run_at: datetime | None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    freshness_seconds: int | None
    consecutive_failures: int = 0
    next_run_at: datetime | None = None
    degraded_reason: str | None = None


class ModelDriftSnapshot(BaseModel):
    snapshot_id: UUID
    tenant_id: str | None = None
    model_name: str
    model_version: str
    drift_score: float
    drift_status: str
    observed_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class ModelTrainingRun(BaseModel):
    run_id: UUID
    model_name: str
    model_version: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    initiated_by: str | None = None
