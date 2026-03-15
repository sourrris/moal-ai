from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from risk_common.connector_abstractions import BaseConnector, register_connector
from risk_common.platform_schema import StandardizedTransaction


@register_connector
class MempoolIngestConnector(BaseConnector):
    def get_source_name(self) -> str:
        return "mempool_bitcoin"

    def verify(self, payload: dict[str, Any]) -> None:
        if not payload.get("txid"):
            raise ValueError("payload.txid is required")
        if payload.get("value") is None:
            raise ValueError("payload.value is required")

    def normalize(self, payload: dict[str, Any], *, tenant_id: str) -> StandardizedTransaction:
        self.verify(payload)
        return StandardizedTransaction(
            transaction_id=str(payload["txid"]),
            tenant_id=tenant_id,
            source="mempool_bitcoin",
            amount=float(payload["value"]) / 100_000_000.0,
            currency="BTC",
            timestamp=datetime.now(tz=UTC),
            counterparty_id=str(payload.get("address")) if payload.get("address") else None,
            metadata_json={
                "vsize": payload.get("vsize"),
                "fee": payload.get("fee"),
                "source_country": payload.get("source_country"),
                "destination_country": payload.get("destination_country"),
            },
        )

    async def healthcheck(self) -> dict[str, Any]:
        return {"status": "ok", "source": self.get_source_name()}


@register_connector
class AbuseChIngestConnector(BaseConnector):
    def get_source_name(self) -> str:
        return "abusech_ip"

    def verify(self, payload: dict[str, Any]) -> None:
        if not payload.get("dst_ip"):
            raise ValueError("payload.dst_ip is required")

    def normalize(self, payload: dict[str, Any], *, tenant_id: str) -> StandardizedTransaction:
        self.verify(payload)
        return StandardizedTransaction(
            transaction_id=str(payload.get("id") or payload["dst_ip"]),
            tenant_id=tenant_id,
            source="abusech_ip",
            amount=float(payload.get("amount") or 1.0),
            currency=str(payload.get("currency") or "USD"),
            timestamp=datetime.now(tz=UTC),
            counterparty_id=str(payload.get("threat")) if payload.get("threat") else None,
            metadata_json={
                "source_ip": payload.get("dst_ip"),
                "source_country": payload.get("source_country"),
                "destination_country": payload.get("destination_country"),
                "threat": payload.get("threat"),
            },
        )

    async def healthcheck(self) -> dict[str, Any]:
        return {"status": "ok", "source": self.get_source_name()}
