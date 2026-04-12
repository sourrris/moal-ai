from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str
    service: str


# -- Behavior Events --

class BehaviorEventIngest(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    user_identifier: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=64)  # auth, api_call, session
    source: str = Field(min_length=1, max_length=120)
    source_ip: str | None = None
    user_agent: str | None = None
    geo_country: str | None = Field(default=None, max_length=8)
    geo_city: str | None = Field(default=None, max_length=120)
    session_duration_seconds: int | None = None
    request_count: int = 0
    failed_auth_count: int = 0
    bytes_transferred: int = 0
    endpoint: str | None = Field(default=None, max_length=512)
    status_code: int | None = None
    device_fingerprint: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class BehaviorEventResponse(BaseModel):
    event_id: UUID
    user_identifier: str
    event_type: str
    source: str
    source_ip: str | None = None
    geo_country: str | None = None
    geo_city: str | None = None
    session_duration_seconds: int | None = None
    request_count: int = 0
    failed_auth_count: int = 0
    endpoint: str | None = None
    status_code: int | None = None
    device_fingerprint: str | None = None
    anomaly_score: float | None = None
    is_anomaly: bool | None = None
    occurred_at: datetime
    ingested_at: datetime


class EventIngestResult(BaseModel):
    event_id: UUID
    status: str  # accepted, duplicate, failed
    anomaly_score: float | None = None
    is_anomaly: bool | None = None


class BatchEventIngest(BaseModel):
    events: list[BehaviorEventIngest] = Field(min_length=1, max_length=500)


class BatchIngestResult(BaseModel):
    accepted: int
    duplicates: int
    failed: int
    results: list[EventIngestResult]


# -- Alerts --

class AlertResponse(BaseModel):
    alert_id: UUID
    event_id: UUID
    severity: str
    anomaly_score: float
    threshold: float
    model_name: str
    model_version: str
    state: str
    user_identifier: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class AlertLifecycleUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


# -- ML Inference --

class InferenceRequest(BaseModel):
    event_id: UUID
    features: list[float]


class InferenceResponse(BaseModel):
    event_id: UUID
    model_name: str
    model_version: str
    anomaly_score: float
    is_anomaly: bool
    threshold: float


# -- Models --

class ModelTrainRequest(BaseModel):
    model_name: str = "behavior_autoencoder"
    training_source: Literal["historical_events", "provided_features"] = "historical_events"
    lookback_hours: int = Field(default=24, ge=1, le=720)
    max_samples: int = Field(default=2048, ge=64, le=20000)
    min_samples: int = Field(default=64, ge=32, le=20000)
    features: list[list[float]] | None = None
    epochs: int = Field(default=12, ge=1, le=500)
    batch_size: int = Field(default=32, ge=1, le=2048)
    threshold_quantile: float = Field(default=0.99, gt=0.5, le=0.9999)
    auto_activate: bool = False

    @model_validator(mode="after")
    def _validate_training_source(self) -> "ModelTrainRequest":
        if self.features and self.training_source == "historical_events":
            self.training_source = "provided_features"
        if self.training_source == "provided_features" and not self.features:
            raise ValueError("features are required when training_source is 'provided_features'")
        return self


class ModelMetadata(BaseModel):
    model_name: str
    model_version: str
    feature_dim: int
    threshold: float
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ModelTrainingResult(BaseModel):
    model_name: str
    model_version: str
    feature_dim: int
    threshold: float
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    sample_count: int
    auto_activated: bool = False
    training_metrics: dict[str, Any] = Field(default_factory=dict)


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
