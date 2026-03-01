from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import set_tenant_context


async def persist_enrichment(
    session: AsyncSession,
    *,
    tenant_id: str,
    event_id: UUID,
    sources: list[dict] | list[str],
    enrichment_payload: dict,
    match_confidence: float | None,
    enrichment_latency_ms: int,
) -> None:
    await set_tenant_context(session, tenant_id)
    await session.execute(
        text(
            """
            INSERT INTO event_enrichments (
                tenant_id,
                event_id,
                sources,
                enrichment_payload,
                match_confidence,
                enrichment_latency_ms
            ) VALUES (
                :tenant_id,
                :event_id,
                CAST(:sources AS JSONB),
                CAST(:enrichment_payload AS JSONB),
                :match_confidence,
                :enrichment_latency_ms
            )
            ON CONFLICT (tenant_id, event_id)
            DO UPDATE SET
                sources = EXCLUDED.sources,
                enrichment_payload = EXCLUDED.enrichment_payload,
                match_confidence = EXCLUDED.match_confidence,
                enrichment_latency_ms = EXCLUDED.enrichment_latency_ms,
                enriched_at = NOW()
            """
        ),
        {
            "tenant_id": tenant_id,
            "event_id": str(event_id),
            "sources": json.dumps(sources),
            "enrichment_payload": json.dumps(enrichment_payload),
            "match_confidence": match_confidence,
            "enrichment_latency_ms": enrichment_latency_ms,
        },
    )


async def persist_decision(
    session: AsyncSession,
    *,
    tenant_id: str,
    event_id: UUID,
    risk_score: float,
    risk_level: str,
    reasons: list[str],
    rule_hits: list[str],
    model_name: str,
    model_version: str,
    ml_anomaly_score: float,
    ml_threshold: float,
    decision_latency_ms: int,
    feature_vector: list[float],
    decision_payload: dict,
) -> dict:
    await set_tenant_context(session, tenant_id)

    row = await session.execute(
        text(
            """
            INSERT INTO risk_decisions (
                tenant_id,
                event_id,
                risk_score,
                risk_level,
                reasons,
                rule_hits,
                model_name,
                model_version,
                ml_anomaly_score,
                ml_threshold,
                decision_latency_ms,
                feature_vector,
                decision_payload
            ) VALUES (
                :tenant_id,
                :event_id,
                :risk_score,
                :risk_level,
                :reasons,
                :rule_hits,
                :model_name,
                :model_version,
                :ml_anomaly_score,
                :ml_threshold,
                :decision_latency_ms,
                :feature_vector,
                CAST(:decision_payload AS JSONB)
            )
            ON CONFLICT (tenant_id, event_id)
            DO UPDATE SET
                risk_score = EXCLUDED.risk_score,
                risk_level = EXCLUDED.risk_level,
                reasons = EXCLUDED.reasons,
                rule_hits = EXCLUDED.rule_hits,
                model_name = EXCLUDED.model_name,
                model_version = EXCLUDED.model_version,
                ml_anomaly_score = EXCLUDED.ml_anomaly_score,
                ml_threshold = EXCLUDED.ml_threshold,
                decision_latency_ms = EXCLUDED.decision_latency_ms,
                feature_vector = EXCLUDED.feature_vector,
                decision_payload = EXCLUDED.decision_payload,
                created_at = NOW()
            RETURNING decision_id, created_at
            """
        ),
        {
            "tenant_id": tenant_id,
            "event_id": str(event_id),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "reasons": reasons,
            "rule_hits": rule_hits,
            "model_name": model_name,
            "model_version": model_version,
            "ml_anomaly_score": ml_anomaly_score,
            "ml_threshold": ml_threshold,
            "decision_latency_ms": decision_latency_ms,
            "feature_vector": feature_vector,
            "decision_payload": json.dumps(decision_payload),
        },
    )
    decision = dict(row.one()._mapping)

    status = "anomaly" if risk_level in {"high", "critical"} else "processed"
    await session.execute(
        text(
            """
            UPDATE events_v2
            SET status = :status
            WHERE tenant_id = :tenant_id
              AND event_id = :event_id
            """
        ),
        {"status": status, "tenant_id": tenant_id, "event_id": str(event_id)},
    )

    if risk_level in {"high", "critical"}:
        await session.execute(
            text(
                """
                INSERT INTO alerts_v2 (
                    tenant_id,
                    event_id,
                    decision_id,
                    state,
                    severity,
                    risk_score,
                    reasons
                ) VALUES (
                    :tenant_id,
                    :event_id,
                    :decision_id,
                    'open',
                    :severity,
                    :risk_score,
                    :reasons
                )
                ON CONFLICT (tenant_id, event_id)
                DO UPDATE SET
                    decision_id = EXCLUDED.decision_id,
                    severity = EXCLUDED.severity,
                    risk_score = EXCLUDED.risk_score,
                    reasons = EXCLUDED.reasons,
                    state = CASE
                        WHEN alerts_v2.state = 'resolved' THEN alerts_v2.state
                        ELSE 'open'
                    END
                """
            ),
            {
                "tenant_id": tenant_id,
                "event_id": str(event_id),
                "decision_id": str(decision["decision_id"]),
                "severity": risk_level,
                "risk_score": risk_score,
                "reasons": reasons,
            },
        )

    await session.commit()
    return decision


async def mark_failed_v2(session: AsyncSession, *, tenant_id: str, event_id: UUID) -> None:
    await set_tenant_context(session, tenant_id)
    await session.execute(
        text(
            """
            UPDATE events_v2
            SET status = 'failed'
            WHERE tenant_id = :tenant_id
              AND event_id = :event_id
            """
        ),
        {"tenant_id": tenant_id, "event_id": str(event_id)},
    )
    await session.commit()
