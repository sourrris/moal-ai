from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EventIngestRequest(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    source: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    features: list[float]
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class EventEnvelope(BaseModel):
    event_id: UUID
    tenant_id: str
    source: str
    event_type: str
    payload: dict[str, Any]
    features: list[float]
    occurred_at: datetime
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class InferenceRequest(BaseModel):
    event_id: UUID
    tenant_id: str
    features: list[float]


class InferenceResponse(BaseModel):
    event_id: UUID
    model_name: str
    model_version: str
    anomaly_score: float
    is_anomaly: bool
    threshold: float


class AlertMessage(BaseModel):
    alert_id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    tenant_id: str
    severity: str = "high"
    model_name: str
    model_version: str
    anomaly_score: float
    threshold: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


T = TypeVar("T")


class WebSocketEnvelope(BaseModel, Generic[T]):
    type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    data: T


class HealthResponse(BaseModel):
    status: str
    service: str


class ModelTrainRequest(BaseModel):
    model_name: str = "risk_autoencoder"
    training_source: Literal["historical_events", "provided_features"] = "historical_events"
    tenant_id: str | None = None
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
        # Backward compatibility: existing clients pass explicit features without training_source.
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
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class ModelListItem(BaseModel):
    model_name: str
    model_version: str
    threshold: float | None = None
    updated_at: datetime | None = None
    inference_count: int = 0
    anomaly_rate: float = 0.0
    active: bool = False
    activate_capable: bool = True
    source: Literal["registry", "inference_only"] = "registry"


class ModelsListResponse(BaseModel):
    active_model: ModelMetadata | None = None
    items: list[ModelListItem] = Field(default_factory=list)


class ModelMetricsPoint(BaseModel):
    bucket: datetime
    avg_threshold: float = 0.0
    avg_score: float = 0.0
    volume: int = 0


class ModelMetricsResponse(BaseModel):
    model_version: str
    anomaly_hit_rate: float = 0.0
    total_inferences: int = 0
    inference_latency_ms: dict[str, float | None] = Field(default_factory=lambda: {"p50": None, "p95": None})
    threshold_evolution: list[ModelMetricsPoint] = Field(default_factory=list)


class ModelTrainResponse(BaseModel):
    run_id: UUID
    status: Literal["running", "success", "failed"]
    model_name: str
    model_version: str | None = None
    feature_dim: int | None = None
    threshold: float | None = None
    updated_at: datetime | None = None
    training_source: Literal["historical_events", "provided_features"] = "historical_events"
    sample_count: int = 0
    auto_activated: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ModelTrainingResult(BaseModel):
    model_name: str
    model_version: str
    feature_dim: int
    threshold: float
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    sample_count: int
    auto_activated: bool = False
    training_metrics: dict[str, Any] = Field(default_factory=dict)
