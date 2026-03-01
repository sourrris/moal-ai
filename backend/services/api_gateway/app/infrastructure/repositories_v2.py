from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from risk_common.schemas_v2 import RiskEventV2
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import set_tenant_context


class EventV2Repository:
    @staticmethod
    async def create_if_absent(
        session: AsyncSession,
        event: RiskEventV2,
    ) -> bool:
        await set_tenant_context(session, event.tenant_id)

        idempotency = await session.execute(
            text(
                """
                INSERT INTO event_idempotency_keys (tenant_id, idempotency_key, event_id)
                VALUES (:tenant_id, :idempotency_key, :event_id)
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                """
            ),
            {
                "tenant_id": event.tenant_id,
                "idempotency_key": event.idempotency_key,
                "event_id": str(event.event_id),
            },
        )
        if not idempotency.rowcount:
            await session.rollback()
            return False

        result = await session.execute(
            text(
                """
                INSERT INTO events_v2 (
                    event_id,
                    tenant_id,
                    idempotency_key,
                    source,
                    event_type,
                    payload,
                    transaction_amount,
                    transaction_currency,
                    source_ip,
                    source_country,
                    destination_country,
                    card_bin,
                    card_last4,
                    user_email_hash,
                    occurred_at,
                    ingested_at,
                    status,
                    submitted_by
                ) VALUES (
                    :event_id,
                    :tenant_id,
                    :idempotency_key,
                    :source,
                    :event_type,
                    CAST(:payload AS JSONB),
                    :transaction_amount,
                    :transaction_currency,
                    :source_ip,
                    :source_country,
                    :destination_country,
                    :card_bin,
                    :card_last4,
                    :user_email_hash,
                    :occurred_at,
                    :ingested_at,
                    :status,
                    :submitted_by
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "event_id": str(event.event_id),
                "tenant_id": event.tenant_id,
                "idempotency_key": event.idempotency_key,
                "source": event.source,
                "event_type": event.event_type,
                "payload": json.dumps(event.transaction.model_dump(mode="json")),
                "transaction_amount": event.transaction.amount,
                "transaction_currency": event.transaction.currency,
                "source_ip": str(event.transaction.source_ip) if event.transaction.source_ip else None,
                "source_country": event.transaction.source_country,
                "destination_country": event.transaction.destination_country,
                "card_bin": event.transaction.card_bin,
                "card_last4": event.transaction.card_last4,
                "user_email_hash": event.transaction.user_email_hash,
                "occurred_at": event.occurred_at,
                "ingested_at": event.ingested_at,
                "status": "queued",
                "submitted_by": event.submitted_by,
            },
        )
        await session.commit()
        return bool(result.rowcount)


class AlertV2Repository:
    @staticmethod
    async def list_alerts(
        session: AsyncSession,
        *,
        tenant_id: str,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> dict:
        await set_tenant_context(session, tenant_id)

        try:
            offset = int(cursor or 0)
        except ValueError:
            offset = 0

        where = ["tenant_id = :tenant_id"]
        params: dict = {"tenant_id": tenant_id, "offset": offset, "limit": limit}
        if state:
            where.append("state = :state")
            params["state"] = state

        where_sql = " AND ".join(where)
        rows = await session.execute(
            text(
                f"""
                SELECT
                    alert_id,
                    event_id,
                    tenant_id,
                    decision_id,
                    state,
                    severity,
                    risk_score,
                    reasons,
                    opened_at,
                    acknowledged_at,
                    resolved_at
                FROM alerts_v2
                WHERE {where_sql}
                ORDER BY opened_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            params,
        )
        total = await session.execute(
            text(f"SELECT COUNT(*) AS total FROM alerts_v2 WHERE {where_sql}"),
            params,
        )
        total_count = int(total.scalar_one() or 0)
        items = [dict(row._mapping) for row in rows]
        next_cursor = str(offset + limit) if offset + limit < total_count else None
        return {"items": items, "next_cursor": next_cursor, "total_estimate": total_count}

    @staticmethod
    async def transition_alert(
        session: AsyncSession,
        *,
        tenant_id: str,
        alert_id: UUID,
        next_state: str,
        actor_id: str,
        note: str | None,
    ) -> dict | None:
        await set_tenant_context(session, tenant_id)

        if next_state == "acknowledged":
            ts_clause = "acknowledged_at = NOW(), resolved_at = NULL"
        elif next_state in {"resolved", "false_positive"}:
            ts_clause = "resolved_at = NOW()"
        else:
            ts_clause = ""

        set_clause = "state = :state"
        if ts_clause:
            set_clause = f"{set_clause}, {ts_clause}"

        row = await session.execute(
            text(
                f"""
                UPDATE alerts_v2
                SET {set_clause}
                WHERE tenant_id = :tenant_id
                  AND alert_id = :alert_id
                RETURNING alert_id, event_id, decision_id, tenant_id, state, severity, risk_score, reasons,
                          opened_at, acknowledged_at, resolved_at
                """
            ),
            {
                "state": next_state,
                "tenant_id": tenant_id,
                "alert_id": str(alert_id),
            },
        )
        updated = row.first()
        if not updated:
            await session.rollback()
            return None

        payload = dict(updated._mapping)
        await session.execute(
            text(
                """
                INSERT INTO decision_audit_log (
                    tenant_id,
                    event_id,
                    decision_id,
                    actor_type,
                    actor_id,
                    action,
                    after_state,
                    reason
                ) VALUES (
                    :tenant_id,
                    :event_id,
                    :decision_id,
                    'analyst',
                    :actor_id,
                    :action,
                    :after_state,
                    :reason
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "event_id": str(payload["event_id"]),
                "decision_id": str(payload["decision_id"]) if payload.get("decision_id") else None,
                "actor_id": actor_id,
                "action": f"alert.{next_state}",
                "after_state": {"state": payload["state"]},
                "reason": note,
            },
        )
        await session.commit()
        return payload


class RiskDecisionRepository:
    @staticmethod
    async def fetch_by_event_id(session: AsyncSession, *, tenant_id: str, event_id: UUID) -> dict | None:
        await set_tenant_context(session, tenant_id)
        row = await session.execute(
            text(
                """
                SELECT
                    decision_id,
                    event_id,
                    tenant_id,
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
                    decision_payload,
                    created_at
                FROM risk_decisions
                WHERE tenant_id = :tenant_id
                  AND event_id = :event_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": str(event_id)},
        )
        item = row.first()
        return dict(item._mapping) if item else None


class DataSourceRepository:
    @staticmethod
    async def list_status(session: AsyncSession) -> list[dict]:
        rows = await session.execute(
            text(
                """
                WITH latest_runs AS (
                    SELECT DISTINCT ON (source_name)
                        source_name,
                        status,
                        started_at
                    FROM connector_runs
                    ORDER BY source_name, started_at DESC
                )
                SELECT
                    es.source_name,
                    COALESCE(scs.enabled, es.enabled) AS enabled,
                    es.cadence_seconds,
                    es.freshness_slo_seconds,
                    lr.status AS latest_status,
                    lr.started_at AS latest_run_at,
                    scs.last_success_at,
                    scs.last_failure_at,
                    CASE
                        WHEN scs.last_success_at IS NULL THEN NULL
                        ELSE EXTRACT(EPOCH FROM (NOW() - scs.last_success_at))::INT
                    END AS freshness_seconds
                    ,
                    COALESCE(scs.consecutive_failures, 0) AS consecutive_failures,
                    scs.next_run_at,
                    scs.degraded_reason
                FROM event_sources es
                LEFT JOIN source_connector_state scs ON scs.source_name = es.source_name
                LEFT JOIN latest_runs lr ON lr.source_name = es.source_name
                ORDER BY es.source_name ASC
                """
            )
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def list_runs(session: AsyncSession, *, source_name: str | None, limit: int) -> list[dict]:
        where = ""
        params: dict = {"limit": limit}
        if source_name:
            where = "WHERE source_name = :source_name"
            params["source_name"] = source_name

        rows = await session.execute(
            text(
                f"""
                SELECT
                    run_id,
                    source_name,
                    status,
                    started_at,
                    finished_at,
                    fetched_records,
                    upserted_records,
                    checksum,
                    cursor_state,
                    details,
                    CASE
                        WHEN status IN ('failed', 'degraded') THEN details
                        ELSE '{{}}'::jsonb
                    END AS error_summary
                FROM connector_runs
                {where}
                ORDER BY started_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        return [dict(row._mapping) for row in rows]


class ModelOpsRepository:
    @staticmethod
    async def list_drift_snapshots(
        session: AsyncSession,
        *,
        tenant_id: str,
        model_name: str | None,
        limit: int,
    ) -> list[dict]:
        await set_tenant_context(session, tenant_id)

        where = "WHERE (tenant_id = :tenant_id OR tenant_id IS NULL)"
        params: dict = {"tenant_id": tenant_id, "limit": limit}
        if model_name:
            where += " AND model_name = :model_name"
            params["model_name"] = model_name

        rows = await session.execute(
            text(
                f"""
                SELECT snapshot_id, tenant_id, model_name, model_version, drift_score, drift_status, observed_at, details
                FROM drift_snapshots
                {where}
                ORDER BY observed_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def list_training_runs(
        session: AsyncSession,
        *,
        model_name: str | None,
        since: datetime | None,
        limit: int,
    ) -> list[dict]:
        where_parts = ["1=1"]
        params: dict = {"limit": limit}
        if model_name:
            where_parts.append("model_name = :model_name")
            params["model_name"] = model_name
        if since:
            where_parts.append("started_at >= :since")
            params["since"] = since

        where_sql = " AND ".join(where_parts)
        rows = await session.execute(
            text(
                f"""
                SELECT run_id, model_name, model_version, status, started_at, finished_at, parameters, metrics, initiated_by
                FROM model_training_runs
                WHERE {where_sql}
                ORDER BY started_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def create_training_run(
        session: AsyncSession,
        *,
        model_name: str,
        parameters: dict[str, Any],
        initiated_by: str | None,
    ) -> UUID:
        row = await session.execute(
            text(
                """
                INSERT INTO model_training_runs (
                    model_name,
                    status,
                    parameters,
                    initiated_by
                ) VALUES (
                    :model_name,
                    'running',
                    CAST(:parameters AS JSONB),
                    :initiated_by
                )
                RETURNING run_id
                """
            ),
            {
                "model_name": model_name,
                "parameters": json.dumps(parameters),
                "initiated_by": initiated_by,
            },
        )
        await session.commit()
        run_id = row.scalar_one()
        return run_id if isinstance(run_id, UUID) else UUID(str(run_id))

    @staticmethod
    async def finalize_training_run(
        session: AsyncSession,
        *,
        run_id: UUID,
        status: str,
        model_version: str | None,
        metrics: dict[str, Any],
        parameters: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> None:
        await session.execute(
            text(
                """
                UPDATE model_training_runs
                SET
                    status = :status,
                    model_version = :model_version,
                    metrics = CAST(:metrics AS JSONB),
                    parameters = COALESCE(CAST(:parameters AS JSONB), parameters),
                    notes = :notes,
                    finished_at = NOW()
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": str(run_id),
                "status": status,
                "model_version": model_version,
                "metrics": json.dumps(metrics),
                "parameters": json.dumps(parameters) if parameters is not None else None,
                "notes": notes,
            },
        )
        await session.commit()
