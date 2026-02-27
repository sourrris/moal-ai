from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


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
    features: list[list[float]]
    epochs: int = 20
    batch_size: int = 32


class ModelMetadata(BaseModel):
    model_name: str
    model_version: str
    feature_dim: int
    threshold: float
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
