from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from risk_common.platform_schema import StandardizedTransaction


class StandardizedInferenceRequest(BaseModel):
    event_id: UUID
    transaction: StandardizedTransaction
    features: list[float] | None = Field(default=None)


def derive_features(transaction: StandardizedTransaction) -> list[float]:
    metadata: dict[str, Any] = transaction.metadata_json or {}
    amount_norm = min(float(transaction.amount) / 10000.0, 1.0)

    source_country = str(metadata.get("source_country") or "").strip()
    destination_country = str(metadata.get("destination_country") or "").strip()
    cross_border = 1.0 if source_country and destination_country and source_country != destination_country else 0.0

    has_ip = 1.0 if metadata.get("source_ip") else 0.0
    has_bin = 1.0 if metadata.get("card_bin") else 0.0
    has_counterparty = 1.0 if transaction.counterparty_id else 0.0
    metadata_density = min(len(metadata) / 10.0, 1.0)
    source_hash = (hash(transaction.source or "") % 1000) / 1000.0
    currency_hash = (hash(transaction.currency or "") % 1000) / 1000.0

    return [
        amount_norm,
        cross_border,
        has_ip,
        has_bin,
        has_counterparty,
        metadata_density,
        source_hash,
        currency_hash,
    ]


__all__ = ["StandardizedInferenceRequest", "derive_features"]
