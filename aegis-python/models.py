from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class StandardizedTransaction:
    transaction_id: str
    tenant_id: str
    source: str
    amount: float
    currency: str
    timestamp: datetime
    counterparty_id: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EventIngestResult:
    event_id: str
    status: str
    queued: bool


@dataclass(slots=True)
class PlatformConfig:
    tenant_id: str
    anomaly_threshold: float | None
    enabled_connectors: list[str]
    model_version: str | None
    rule_overrides_json: dict[str, Any]
    connector_modules_loaded: list[str]
