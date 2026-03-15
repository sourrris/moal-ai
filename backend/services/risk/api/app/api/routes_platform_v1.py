from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from risk_common.connector_abstractions import (
    BaseConnector,
    connector_registry,
    load_connector_from_config,
    register_connector,
)
from risk_common.platform_schema import StandardizedTransaction
from risk_common.schemas_v2 import AuthClaims, EventIngestResult
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_rabbit_channel, require_scope
from app.api.routes_events_v2 import _ingest_single_event
from app.config import get_settings
from app.infrastructure.db import get_db_session
from app.infrastructure.monitoring_repository import MonitoringRepository
from app.infrastructure.operational_repository_v2 import AlertV2Repository

router = APIRouter(prefix="/api/v1", tags=["platform-api-v1"])
settings = get_settings()
logger = logging.getLogger(__name__)


class PlatformIngestRequest(BaseModel):
    connector: str | None = None
    source: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    transaction: StandardizedTransaction | None = None
    event_type: str = "transaction"
    idempotency_key: str | None = None
    occurred_at: datetime | None = None


class PlatformConfigResponse(BaseModel):
    tenant_id: str
    anomaly_threshold: float | None = None
    enabled_connectors: list[str] = Field(default_factory=list)
    model_version: str | None = None
    rule_overrides_json: dict[str, Any] = Field(default_factory=dict)
    connector_modules_loaded: list[str] = Field(default_factory=list)


def _route_map() -> dict[str, str]:
    raw = settings.connector_source_route_map_json or "{}"
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): str(value) for key, value in loaded.items() if key and value}


@register_connector
class GenericTransactionConnector(BaseConnector):
    def get_source_name(self) -> str:
        return "generic_transaction"

    def verify(self, payload: dict[str, Any]) -> None:
        if not payload.get("transaction_id"):
            raise ValueError("payload.transaction_id is required")
        if payload.get("amount") is None:
            raise ValueError("payload.amount is required")
        if not payload.get("currency"):
            raise ValueError("payload.currency is required")

    def normalize(self, payload: dict[str, Any], *, tenant_id: str) -> StandardizedTransaction:
        self.verify(payload)
        metadata = dict(payload.get("metadata_json") or payload.get("metadata") or {})
        metadata.setdefault("source_country", payload.get("source_country"))
        metadata.setdefault("destination_country", payload.get("destination_country"))
        metadata.setdefault("source_ip", payload.get("source_ip"))
        metadata.setdefault("card_bin", payload.get("card_bin"))
        metadata.setdefault("card_last4", payload.get("card_last4"))
        metadata.setdefault("merchant_id", payload.get("counterparty_id") or payload.get("merchant_id"))
        metadata.setdefault("merchant_category", payload.get("merchant_category"))
        metadata.setdefault("user_email_hash", payload.get("user_email_hash"))
        metadata.setdefault("event_type", payload.get("event_type") or "transaction")
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, str):
            occurred_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif isinstance(timestamp, datetime):
            occurred_at = timestamp
        else:
            occurred_at = datetime.now(tz=UTC)

        return StandardizedTransaction(
            transaction_id=str(payload["transaction_id"]),
            tenant_id=tenant_id,
            source=str(payload.get("source") or "generic_transaction"),
            amount=float(payload["amount"]),
            currency=str(payload["currency"]).upper(),
            timestamp=occurred_at,
            counterparty_id=(
                str(payload["counterparty_id"])
                if payload.get("counterparty_id")
                else str(payload["merchant_id"])
                if payload.get("merchant_id")
                else None
            ),
            metadata_json=metadata,
        )

    async def healthcheck(self) -> dict[str, Any]:
        return {"status": "ok", "source": self.get_source_name()}


CONNECTOR_MODULES_LOADED: list[str] = []
try:
    CONNECTOR_MODULES_LOADED = load_connector_from_config(settings.connector_ingest_modules)
except Exception as exc:  # noqa: BLE001
    logger.warning("platform_v1_connector_module_load_failed", extra={"error": str(exc)})


def _resolve_connector_name(request: PlatformIngestRequest) -> str:
    if request.connector:
        return request.connector

    source_hint = request.source or str(request.payload.get("source") or "")
    if source_hint:
        mapped = _route_map().get(source_hint)
        return mapped or source_hint
    return "generic_transaction"


def _build_standardized_transaction(request: PlatformIngestRequest, *, tenant_id: str) -> StandardizedTransaction:
    if request.transaction:
        tx = request.transaction
        tx.tenant_id = tenant_id
        return tx

    source = _resolve_connector_name(request)
    connector = connector_registry.get(source)
    if connector is None:
        raise HTTPException(status_code=404, detail=f"No connector registered for source '{source}'")

    try:
        return connector.normalize(request.payload, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Connector payload validation failed: {exc}") from exc


@router.post("/ingest", response_model=EventIngestResult)
async def ingest_platform_event(
    payload: PlatformIngestRequest,
    claims: AuthClaims = Depends(require_scope("events:write")),
    session: AsyncSession = Depends(get_db_session),
    channel=Depends(get_rabbit_channel),
) -> EventIngestResult:
    standardized = _build_standardized_transaction(payload, tenant_id=claims.tenant_id)
    if claims.domain_hostname:
        standardized.metadata_json.setdefault("registered_domain", claims.domain_hostname)
    if claims.domain_id:
        standardized.metadata_json.setdefault("registered_domain_id", claims.domain_id)
    if claims.key_prefix:
        standardized.metadata_json.setdefault("ingest_api_key", claims.key_prefix)
    event = standardized.to_risk_event_ingest_request(
        event_type=payload.event_type,
        idempotency_key=payload.idempotency_key,
    )
    if payload.occurred_at:
        event.occurred_at = payload.occurred_at

    return await _ingest_single_event(event, claims, session, channel)


@router.get("/alerts")
async def list_alerts_platform(
    state: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    claims: AuthClaims = Depends(require_scope("alerts:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await AlertV2Repository.list_alerts(
        session,
        tenant_id=claims.tenant_id,
        state=state,
        cursor=cursor,
        limit=limit,
    )


@router.get("/metrics")
async def metrics_platform(
    window: str = Query(default="24h"),
    claims: AuthClaims = Depends(require_scope("alerts:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    window_to_hours = {"1h": 1, "24h": 24, "7d": 24 * 7}
    hours = window_to_hours.get(window, 24)
    from_ts = datetime.now(tz=UTC) - timedelta(hours=hours)
    return await MonitoringRepository.overview_metrics(
        session,
        tenant_id=claims.tenant_id,
        from_ts=from_ts,
        window_hours=hours,
    )


@router.get("/config", response_model=PlatformConfigResponse)
async def config_platform(
    claims: AuthClaims = Depends(require_scope("events:read")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformConfigResponse:
    row = await session.execute(
        text(
            """
            SELECT tenant_id, anomaly_threshold, enabled_connectors, model_version, rule_overrides_json
            FROM tenant_configuration
            WHERE tenant_id = :tenant_id
            LIMIT 1
            """
        ),
        {"tenant_id": claims.tenant_id},
    )
    item = row.first()
    if not item:
        return PlatformConfigResponse(tenant_id=claims.tenant_id, connector_modules_loaded=CONNECTOR_MODULES_LOADED)

    mapping = dict(item._mapping)
    enabled_connectors = mapping.get("enabled_connectors")
    if not isinstance(enabled_connectors, list):
        enabled_connectors = []
    overrides = mapping.get("rule_overrides_json")
    if not isinstance(overrides, dict):
        overrides = {}

    return PlatformConfigResponse(
        tenant_id=str(mapping.get("tenant_id") or claims.tenant_id),
        anomaly_threshold=float(mapping["anomaly_threshold"]) if mapping.get("anomaly_threshold") is not None else None,
        enabled_connectors=[str(item) for item in enabled_connectors],
        model_version=str(mapping["model_version"]) if mapping.get("model_version") else None,
        rule_overrides_json=overrides,
        connector_modules_loaded=CONNECTOR_MODULES_LOADED,
    )
