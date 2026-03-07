from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from risk_common.schemas import EventEnvelope
from risk_common.schemas_v2 import RiskEventIngestRequest, RiskEventV2, TransactionPayload


class StandardizedTransaction(BaseModel):
    transaction_id: str
    tenant_id: str
    source: str
    amount: float
    currency: str
    timestamp: datetime
    counterparty_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_event_v2(cls, event: RiskEventV2) -> "StandardizedTransaction":
        tx = event.transaction
        counterparty = tx.merchant_id or tx.user_email_hash or tx.transaction_id
        metadata = dict(tx.metadata)
        metadata.setdefault("event_id", str(event.event_id))
        metadata.setdefault("event_type", event.event_type)
        metadata.setdefault("source_country", tx.source_country)
        metadata.setdefault("destination_country", tx.destination_country)
        metadata.setdefault("source_ip", str(tx.source_ip) if tx.source_ip else None)
        metadata.setdefault("card_bin", tx.card_bin)
        metadata.setdefault("card_last4", tx.card_last4)
        metadata.setdefault("merchant_category", tx.merchant_category)
        return cls(
            transaction_id=tx.transaction_id or str(event.event_id),
            tenant_id=event.tenant_id,
            source=event.source,
            amount=float(tx.amount),
            currency=tx.currency,
            timestamp=event.occurred_at,
            counterparty_id=counterparty,
            metadata_json=metadata,
        )

    @classmethod
    def from_event_envelope(cls, event: EventEnvelope) -> "StandardizedTransaction":
        payload = dict(event.payload)
        counterparty = payload.get("merchant_id") or payload.get("user_email_hash") or payload.get("counterparty_id")
        amount_raw = payload.get("amount", 0.0)
        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            amount = 0.0

        timestamp = event.occurred_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            transaction_id=str(payload.get("transaction_id") or event.event_id),
            tenant_id=event.tenant_id,
            source=event.source,
            amount=amount,
            currency=str(payload.get("currency") or "USD").upper(),
            timestamp=timestamp,
            counterparty_id=str(counterparty) if counterparty else None,
            metadata_json=payload,
        )

    def to_transaction_payload(self) -> TransactionPayload:
        metadata = dict(self.metadata_json)
        metadata.setdefault("counterparty_id", self.counterparty_id)
        return TransactionPayload(
            transaction_id=self.transaction_id,
            amount=float(self.amount),
            currency=self.currency,
            source_ip=metadata.get("source_ip"),
            source_country=metadata.get("source_country"),
            destination_country=metadata.get("destination_country"),
            card_bin=metadata.get("card_bin"),
            card_last4=metadata.get("card_last4"),
            merchant_id=metadata.get("merchant_id") or self.counterparty_id,
            merchant_category=metadata.get("merchant_category"),
            user_email_hash=metadata.get("user_email_hash"),
            metadata=metadata,
        )

    def to_risk_event_ingest_request(
        self,
        *,
        event_id: UUID | None = None,
        idempotency_key: str | None = None,
        event_type: str = "transaction",
    ) -> RiskEventIngestRequest:
        normalized_event_id = event_id or uuid4()
        key = idempotency_key or f"std-{self.source}-{self.transaction_id}-{normalized_event_id}"
        return RiskEventIngestRequest(
            event_id=normalized_event_id,
            idempotency_key=key[:128],
            source=self.source,
            event_type=event_type,
            transaction=self.to_transaction_payload(),
            occurred_at=self.timestamp,
        )


class StandardizedAlert(BaseModel):
    alert_id: UUID = Field(default_factory=uuid4)
    transaction_id: str
    tenant_id: str
    anomaly_score: float
    severity: str
    model_version: str
    explanation_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


__all__ = ["StandardizedTransaction", "StandardizedAlert"]
