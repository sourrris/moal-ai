import json
import logging
import time
from uuid import UUID

import httpx
from aio_pika import IncomingMessage
from redis.asyncio import Redis
from risk_common.messaging import publish_json_with_compat
from risk_common.platform_schema import StandardizedAlert, StandardizedTransaction
from risk_common.schemas import (
    AlertMessage,
    EventEnvelope,
    InferenceResponse,
    WebSocketEnvelope,
)
from risk_common.schemas_v2 import RiskEventV2

from app.application.enrichment import EventEnrichmentService
from app.application.rules_engine import RulesEngine, infer_risk_level
from app.config import get_settings
from app.infrastructure.db import SessionLocal
from app.infrastructure.event_repository import mark_failed, persist_inference
from app.infrastructure.event_repository_v2 import (
    mark_failed_v2,
    persist_decision,
    persist_enrichment,
)
from app.infrastructure.tenant_config_repository import (
    TenantConfigRepository,
    TenantProcessingConfig,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class TenantConfigError(RuntimeError):
    pass


class EventProcessor:
    def __init__(self, redis_client: Redis, rabbit_channel):
        self.redis = redis_client
        self.rabbit_channel = rabbit_channel

    async def handle_message(self, message: IncomingMessage) -> None:
        event_id: UUID | None = None
        payload: dict | None = None

        try:
            payload = json.loads(message.body)
            event = EventEnvelope(**payload)
            transaction = StandardizedTransaction.from_event_envelope(event)
            event_id = event.event_id

            processed_key = f"processed:{event.event_id}"
            if await self.redis.get(processed_key):
                await message.ack()
                return

            inference = await self._call_inference(event.event_id, transaction, event.features)

            async with SessionLocal() as session:
                await persist_inference(
                    session=session,
                    event_id=event.event_id,
                    model_name=inference.model_name,
                    model_version=inference.model_version,
                    score=inference.anomaly_score,
                    threshold=inference.threshold,
                    is_anomaly=inference.is_anomaly,
                )

            if inference.is_anomaly:
                standardized_alert = StandardizedAlert(
                    transaction_id=transaction.transaction_id,
                    tenant_id=transaction.tenant_id,
                    anomaly_score=inference.anomaly_score,
                    severity="high",
                    model_version=inference.model_version,
                    explanation_json={
                        "event_id": str(event.event_id),
                        "source": transaction.source,
                        "threshold": inference.threshold,
                    },
                )
                alert = AlertMessage(
                    alert_id=standardized_alert.alert_id,
                    event_id=event.event_id,
                    tenant_id=event.tenant_id,
                    model_name=inference.model_name,
                    model_version=inference.model_version,
                    anomaly_score=inference.anomaly_score,
                    threshold=inference.threshold,
                )
                envelope = WebSocketEnvelope[AlertMessage](type="ALERT_CREATED", data=alert)
                await publish_json_with_compat(
                    channel=self.rabbit_channel,
                    exchange_name=settings.rabbitmq_alerts_exchange,
                    routing_key=settings.rabbitmq_alerts_routing_key,
                    payload=envelope.model_dump(mode="json"),
                    legacy_exchange_name=settings.rabbitmq_alerts_exchange_legacy,
                    legacy_routing_key=settings.rabbitmq_alerts_routing_key_legacy,
                )

            await self.redis.set(processed_key, "1", ex=settings.dedupe_ttl_seconds)
            await message.ack()

        except Exception as exc:  # noqa: BLE001
            logger.exception("worker_process_failed", extra={"error": str(exc)})
            await self._retry_or_dead_letter(message, payload, event_id)

    async def handle_message_v2(self, message: IncomingMessage) -> None:
        event_id: UUID | None = None
        tenant_id: str | None = None
        payload: dict | None = None

        try:
            payload = json.loads(message.body)
            event = RiskEventV2(**payload)
            event_id = event.event_id
            tenant_id = event.tenant_id

            processed_key = f"processed:v2:{event.tenant_id}:{event.event_id}"
            if await self.redis.get(processed_key):
                await message.ack()
                return

            standardized_tx = StandardizedTransaction.from_event_v2(event)
            tenant_config = await self._resolve_tenant_config(standardized_tx.tenant_id)
            self._assert_source_enabled(event.source, tenant_config)

            started = time.perf_counter()
            enrichment, provenance, enrichment_latency_ms = await self._resolve_enrichment_v2(event)
            async with SessionLocal() as session:
                await persist_enrichment(
                    session,
                    tenant_id=event.tenant_id,
                    event_id=event.event_id,
                    sources=provenance,
                    enrichment_payload=enrichment,
                    match_confidence=0.98 if enrichment.get("sanctions_hit") else 0.7,
                    enrichment_latency_ms=enrichment_latency_ms,
                )

            features = self._build_feature_vector(standardized_tx, enrichment)
            inference = await self._call_inference(event.event_id, standardized_tx, features)
            threshold = self._resolve_threshold(inference, tenant_config)
            inference_is_anomaly = inference.anomaly_score > threshold
            rule_hits, rule_score = RulesEngine.evaluate(
                event,
                enrichment,
                overrides=tenant_config.rule_overrides if tenant_config else None,
            )

            ml_component = min(inference.anomaly_score / max(threshold, 1e-6), 2.0) / 2.0
            risk_score = min(1.0, (0.65 * ml_component) + (0.35 * rule_score))
            if enrichment.get("sanctions_hit") and risk_score < 0.85:
                risk_score = 0.85
            risk_level = infer_risk_level(risk_score)

            reasons = [*rule_hits]
            if inference_is_anomaly:
                reasons.append("ml_threshold_breach")
            if not reasons:
                reasons.append("baseline")

            effective_model_version = (
                tenant_config.model_version
                if tenant_config and tenant_config.model_version
                else inference.model_version
            )
            decision_latency_ms = int((time.perf_counter() - started) * 1000)
            async with SessionLocal() as session:
                decision = await persist_decision(
                    session,
                    tenant_id=event.tenant_id,
                    event_id=event.event_id,
                    risk_score=risk_score,
                    risk_level=risk_level,
                    reasons=reasons,
                    rule_hits=rule_hits,
                    model_name=inference.model_name,
                    model_version=effective_model_version,
                    ml_anomaly_score=inference.anomaly_score,
                    ml_threshold=threshold,
                    decision_latency_ms=decision_latency_ms,
                    feature_vector=features,
                    decision_payload={
                        "enrichment": enrichment,
                        "transaction": event.transaction.model_dump(mode="json"),
                        "standardized_transaction": standardized_tx.model_dump(mode="json"),
                        "tenant_config": {
                            "anomaly_threshold": tenant_config.anomaly_threshold if tenant_config else None,
                            "model_version": tenant_config.model_version if tenant_config else None,
                            "rule_overrides": tenant_config.rule_overrides if tenant_config else {},
                        },
                        "schema_version": 2,
                    },
                )

            if risk_level in {"high", "critical"}:
                standardized_alert = StandardizedAlert(
                    transaction_id=standardized_tx.transaction_id,
                    tenant_id=standardized_tx.tenant_id,
                    anomaly_score=inference.anomaly_score,
                    severity=risk_level,
                    model_version=effective_model_version,
                    explanation_json={
                        "reasons": reasons,
                        "threshold": threshold,
                        "risk_score": risk_score,
                    },
                )
                alert_payload = {
                    "alert_id": str(standardized_alert.alert_id),
                    "event_id": str(event.event_id),
                    "tenant_id": event.tenant_id,
                    "severity": risk_level,
                    "risk_score": risk_score,
                    "reasons": reasons,
                    "decision_id": str(decision["decision_id"]),
                    "created_at": decision["created_at"],
                }
                envelope = WebSocketEnvelope[dict](type="ALERT_V2_CREATED", data=alert_payload)
                await publish_json_with_compat(
                    channel=self.rabbit_channel,
                    exchange_name=settings.rabbitmq_alerts_exchange,
                    routing_key=settings.rabbitmq_alerts_routing_key,
                    payload=envelope.model_dump(mode="json"),
                    legacy_exchange_name=settings.rabbitmq_alerts_exchange_legacy,
                    legacy_routing_key=settings.rabbitmq_alerts_routing_key_legacy,
                )

            await publish_json_with_compat(
                channel=self.rabbit_channel,
                exchange_name=settings.rabbitmq_metrics_exchange,
                routing_key=settings.rabbitmq_metrics_routing_key,
                payload={
                    "tenant_id": event.tenant_id,
                    "event_id": str(event.event_id),
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "decision_latency_ms": decision_latency_ms,
                    "occurred_at": event.occurred_at,
                    "processed_at": time.time(),
                },
                headers={"x-schema-version": 2},
                legacy_exchange_name=settings.rabbitmq_metrics_exchange_legacy,
                legacy_routing_key=settings.rabbitmq_metrics_routing_key_legacy,
            )

            await self.redis.set(processed_key, "1", ex=settings.dedupe_ttl_seconds)
            await message.ack()

        except TenantConfigError as exc:
            logger.warning("worker_process_v2_config_failed", extra={"error": str(exc), "tenant_id": tenant_id})
            await self._dead_letter_non_retryable_v2(message, payload, event_id, tenant_id, reason=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("worker_process_v2_failed", extra={"error": str(exc)})
            await self._retry_or_dead_letter_v2(message, payload, event_id, tenant_id)

    async def _resolve_enrichment_v2(self, event: RiskEventV2) -> tuple[dict, list[dict], int]:
        payload = {
            "tenant_id": event.tenant_id,
            "source_ip": str(event.transaction.source_ip) if event.transaction.source_ip else None,
            "card_bin": event.transaction.card_bin,
            "source_country": event.transaction.source_country,
            "destination_country": event.transaction.destination_country,
            "merchant_name": event.transaction.merchant_id or event.transaction.metadata.get("merchant_name"),
            "currency": event.transaction.currency,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{settings.feature_enrichment_url}/v1/enrichment/resolve",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            signals = data.get("signals") if isinstance(data, dict) else {}
            provenance = data.get("provenance") if isinstance(data, dict) else []
            latency_ms = data.get("enrichment_latency_ms") if isinstance(data, dict) else None
            normalized_signals = signals if isinstance(signals, dict) else {}
            normalized_provenance = provenance if isinstance(provenance, list) else []
            if latency_ms is None:
                latency_ms = int((time.perf_counter() - started) * 1000)
            return normalized_signals, normalized_provenance, int(latency_ms)
        except Exception:  # noqa: BLE001
            async with SessionLocal() as session:
                signals, sources = await EventEnrichmentService.enrich(session, event)
            fallback_provenance = [{"source": source, "cache_hit": True, "mode": "db_fallback"} for source in sources]
            latency_ms = int((time.perf_counter() - started) * 1000)
            return signals, fallback_provenance, latency_ms

    async def _call_inference(
        self,
        event_id: UUID,
        transaction: StandardizedTransaction,
        features: list[float],
    ) -> InferenceResponse:
        req = {
            "event_id": str(event_id),
            "transaction": transaction.model_dump(mode="json"),
            "features": features,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{settings.ml_inference_url}/v1/infer/standardized",
                json=req,
            )
            response.raise_for_status()
            return InferenceResponse(**response.json())

    @staticmethod
    def _build_feature_vector(transaction: StandardizedTransaction, enrichment: dict) -> list[float]:
        metadata = transaction.metadata_json
        amount_usd = float(transaction.amount) * float(enrichment.get("fx_rate") or 1.0)
        amount_norm = min(amount_usd / 10000.0, 1.0)

        cross_border = 0.0
        source_country = str(metadata.get("source_country") or "").strip()
        destination_country = str(metadata.get("destination_country") or "").strip()
        if source_country and destination_country and source_country.upper() != destination_country.upper():
            cross_border = 1.0

        ip_risk_score = min(max(float(enrichment.get("ip_risk_score") or 0.0), 0.0), 1.0)
        bin_mismatch = 1.0 if enrichment.get("bin_country_mismatch") else 0.0
        jurisdiction_risk = min(max(float(enrichment.get("jurisdiction_risk_score") or 0.0), 0.0), 1.0)
        sanctions_hit = 1.0 if enrichment.get("sanctions_hit") else 0.0
        pep_hit = 1.0 if enrichment.get("pep_hit") else 0.0
        metadata_density = min(len(metadata) / 10.0, 1.0)

        return [
            amount_norm,
            cross_border,
            ip_risk_score,
            bin_mismatch,
            jurisdiction_risk,
            sanctions_hit,
            pep_hit,
            metadata_density,
        ]

    @staticmethod
    def _resolve_threshold(inference: InferenceResponse, tenant_config: TenantProcessingConfig | None) -> float:
        if not tenant_config:
            return inference.threshold
        if tenant_config.anomaly_threshold is None:
            return inference.threshold
        return float(tenant_config.anomaly_threshold)

    @staticmethod
    def _assert_source_enabled(source: str, tenant_config: TenantProcessingConfig | None) -> None:
        if tenant_config is None:
            return
        if not tenant_config.enabled_connectors:
            return
        if source in tenant_config.enabled_connectors:
            return
        raise TenantConfigError(f"Source '{source}' is disabled for tenant '{tenant_config.tenant_id}'")

    async def _resolve_tenant_config(self, tenant_id: str) -> TenantProcessingConfig | None:
        async with SessionLocal() as session:
            config = await TenantConfigRepository.fetch(session, tenant_id)
        if config is not None:
            return config
        mode = str(settings.tenant_config_enforcement_mode or "permissive").strip().lower()
        if mode == "strict":
            raise TenantConfigError(f"Missing tenant configuration for tenant '{tenant_id}'")
        return None

    async def _retry_or_dead_letter(
        self,
        message: IncomingMessage,
        payload: dict | None,
        event_id: UUID | None,
    ) -> None:
        headers = dict(message.headers or {})
        retry_count = int(headers.get("x-retry-count", 0))

        if payload is None:
            await message.ack()
            return

        if retry_count < settings.max_event_retries:
            headers["x-retry-count"] = retry_count + 1
            await publish_json_with_compat(
                channel=self.rabbit_channel,
                exchange_name=settings.rabbitmq_events_exchange,
                routing_key=settings.rabbitmq_events_routing_key,
                payload=payload,
                headers=headers,
                legacy_exchange_name=settings.rabbitmq_events_exchange_legacy,
                legacy_routing_key=settings.rabbitmq_events_routing_key_legacy,
            )
            await message.ack()
            return

        await publish_json_with_compat(
            channel=self.rabbit_channel,
            exchange_name=settings.rabbitmq_dlx_exchange,
            routing_key=settings.rabbitmq_events_routing_key,
            payload=payload,
            headers={"x-dead-letter-reason": "max-retries-exceeded"},
            legacy_exchange_name=settings.rabbitmq_dlx_exchange_legacy,
            legacy_routing_key=settings.rabbitmq_events_routing_key_legacy,
        )

        if event_id is not None:
            async with SessionLocal() as session:
                await mark_failed(session, event_id)

        await message.ack()

    async def _retry_or_dead_letter_v2(
        self,
        message: IncomingMessage,
        payload: dict | None,
        event_id: UUID | None,
        tenant_id: str | None,
    ) -> None:
        headers = dict(message.headers or {})
        retry_count = int(headers.get("x-retry-count", 0))

        if payload is None:
            await message.ack()
            return

        if retry_count < settings.max_event_retries:
            headers["x-retry-count"] = retry_count + 1
            await publish_json_with_compat(
                channel=self.rabbit_channel,
                exchange_name=settings.rabbitmq_events_exchange,
                routing_key=settings.rabbitmq_events_v2_routing_key,
                payload=payload,
                headers=headers,
                legacy_exchange_name=settings.rabbitmq_events_exchange_legacy,
                legacy_routing_key=settings.rabbitmq_events_v2_routing_key_legacy,
            )
            await message.ack()
            return

        await publish_json_with_compat(
            channel=self.rabbit_channel,
            exchange_name=settings.rabbitmq_dlx_exchange,
            routing_key=settings.rabbitmq_events_v2_routing_key,
            payload=payload,
            headers={"x-dead-letter-reason": "max-retries-exceeded"},
            legacy_exchange_name=settings.rabbitmq_dlx_exchange_legacy,
            legacy_routing_key=settings.rabbitmq_events_v2_routing_key_legacy,
        )

        if event_id is not None and tenant_id:
            async with SessionLocal() as session:
                await mark_failed_v2(session, tenant_id=tenant_id, event_id=event_id)

        await message.ack()

    async def _dead_letter_non_retryable_v2(
        self,
        message: IncomingMessage,
        payload: dict | None,
        event_id: UUID | None,
        tenant_id: str | None,
        *,
        reason: str,
    ) -> None:
        if payload is not None:
            await publish_json_with_compat(
                channel=self.rabbit_channel,
                exchange_name=settings.rabbitmq_dlx_exchange,
                routing_key=settings.rabbitmq_events_v2_routing_key,
                payload=payload,
                headers={"x-dead-letter-reason": reason[:180], "x-schema-version": 2},
                legacy_exchange_name=settings.rabbitmq_dlx_exchange_legacy,
                legacy_routing_key=settings.rabbitmq_events_v2_routing_key_legacy,
            )
        if event_id is not None and tenant_id:
            async with SessionLocal() as session:
                await mark_failed_v2(session, tenant_id=tenant_id, event_id=event_id)
        await message.ack()
