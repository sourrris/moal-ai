from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import set_tenant_context

ALLOWED_RULE_KEYS = {
    "high_amount_threshold",
    "high_amount_weight",
    "sanctions_weight",
    "pep_weight",
    "proxy_ip_weight",
    "bin_mismatch_weight",
    "jurisdiction_threshold",
    "jurisdiction_weight",
    "cross_border_weight",
}


def _json(value: dict | list | None, *, default_obj: str = "{}") -> str:
    if value is None:
        return default_obj
    return json.dumps(value, default=str)


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _to_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return []
    return []


class ControlRepository:
    @staticmethod
    async def list_tenants(session: AsyncSession, *, status: str | None, limit: int, offset: int) -> list[dict]:
        where = ""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            where = "WHERE status = :status"
            params["status"] = status

        rows = await session.execute(
            text(
                f"""
                SELECT tenant_id, display_name, status, tier, metadata, created_at, updated_at
                FROM tenants
                {where}
                ORDER BY tenant_id ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row._mapping)
            item["metadata_json"] = _to_dict(item.pop("metadata", {}))
            results.append(item)
        return results

    @staticmethod
    async def get_tenant(session: AsyncSession, tenant_id: str) -> dict | None:
        row = await session.execute(
            text(
                """
                SELECT tenant_id, display_name, status, tier, metadata, created_at, updated_at
                FROM tenants
                WHERE tenant_id = :tenant_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        item = row.first()
        if not item:
            return None
        result = dict(item._mapping)
        result["metadata_json"] = _to_dict(result.pop("metadata", {}))
        return result

    @staticmethod
    async def create_tenant(
        session: AsyncSession,
        *,
        tenant_id: str,
        display_name: str,
        status: str,
        tier: str,
        metadata_json: dict[str, Any],
    ) -> dict:
        existing = await ControlRepository.get_tenant(session, tenant_id)
        if existing:
            raise ValueError(f"Tenant '{tenant_id}' already exists")

        await session.execute(
            text(
                """
                INSERT INTO tenants (tenant_id, display_name, status, tier, metadata, created_at, updated_at)
                VALUES (:tenant_id, :display_name, :status, :tier, CAST(:metadata AS jsonb), NOW(), NOW())
                """
            ),
            {
                "tenant_id": tenant_id,
                "display_name": display_name,
                "status": status,
                "tier": tier,
                "metadata": _json(metadata_json),
            },
        )

        await session.execute(
            text(
                """
                INSERT INTO tenant_configuration (
                    tenant_id,
                    anomaly_threshold,
                    enabled_connectors,
                    model_version,
                    rule_overrides_json,
                    version,
                    created_at,
                    updated_at
                )
                VALUES (
                    :tenant_id,
                    NULL,
                    '[]'::jsonb,
                    NULL,
                    '{}'::jsonb,
                    1,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (tenant_id) DO NOTHING
                """
            ),
            {"tenant_id": tenant_id},
        )

        await session.execute(
            text(
                """
                INSERT INTO control_alert_routing_policy (tenant_id, policy_json, updated_by, updated_at)
                VALUES (:tenant_id, '{}'::jsonb, 'system', NOW())
                ON CONFLICT (tenant_id) DO NOTHING
                """
            ),
            {"tenant_id": tenant_id},
        )

        await session.commit()
        tenant = await ControlRepository.get_tenant(session, tenant_id)
        if not tenant:
            raise RuntimeError("Created tenant not found")
        return tenant

    @staticmethod
    async def update_tenant(
        session: AsyncSession,
        *,
        tenant_id: str,
        display_name: str | None,
        status: str | None,
        tier: str | None,
        metadata_json: dict[str, Any] | None,
    ) -> dict | None:
        existing = await ControlRepository.get_tenant(session, tenant_id)
        if not existing:
            return None

        await session.execute(
            text(
                """
                UPDATE tenants
                SET display_name = COALESCE(:display_name, display_name),
                    status = COALESCE(:status, status),
                    tier = COALESCE(:tier, tier),
                    metadata = COALESCE(CAST(:metadata AS jsonb), metadata),
                    updated_at = NOW()
                WHERE tenant_id = :tenant_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "display_name": display_name,
                "status": status,
                "tier": tier,
                "metadata": _json(metadata_json) if metadata_json is not None else None,
            },
        )
        await session.commit()
        return await ControlRepository.get_tenant(session, tenant_id)

    @staticmethod
    async def assign_tenant_admin(
        session: AsyncSession,
        *,
        tenant_id: str,
        username: str,
        role_name: str,
    ) -> dict:
        tenant = await ControlRepository.get_tenant(session, tenant_id)
        if not tenant:
            raise ValueError(f"Unknown tenant '{tenant_id}'")

        user_row = await session.execute(
            text("SELECT id, username FROM users WHERE username = :username LIMIT 1"),
            {"username": username},
        )
        user = user_row.first()
        if not user:
            raise ValueError(f"Unknown user '{username}'")

        role_row = await session.execute(
            text("SELECT role_name FROM roles WHERE role_name = :role_name LIMIT 1"),
            {"role_name": role_name},
        )
        if role_row.first() is None:
            raise ValueError(f"Unknown role '{role_name}'")

        user_id = int(user._mapping["id"])
        await session.execute(
            text(
                """
                INSERT INTO user_tenant_roles (user_id, tenant_id, role_name)
                VALUES (:user_id, :tenant_id, :role_name)
                ON CONFLICT (user_id, tenant_id, role_name) DO NOTHING
                """
            ),
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "role_name": role_name,
            },
        )
        await session.commit()
        return {
            "tenant_id": tenant_id,
            "username": username,
            "role_name": role_name,
            "assigned": True,
        }

    @staticmethod
    async def get_active_global_model_version(session: AsyncSession) -> str | None:
        try:
            row = await session.execute(
                text(
                    """
                    SELECT model_version
                    FROM model_registry
                    WHERE active = TRUE
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                )
            )
            version = row.scalar_one_or_none()
            if version:
                return str(version)
        except SQLAlchemyError:
            await session.rollback()

        try:
            row_v2 = await session.execute(
                text(
                    """
                    SELECT model_version
                    FROM model_registry_v2
                    WHERE status = 'active'
                    ORDER BY COALESCE(activated_at, created_at) DESC
                    LIMIT 1
                    """
                )
            )
            version_v2 = row_v2.scalar_one_or_none()
            return str(version_v2) if version_v2 else None
        except SQLAlchemyError:
            await session.rollback()
            return None

    @staticmethod
    async def list_connector_catalog(session: AsyncSession) -> list[dict]:
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
                    es.source_type,
                    es.enabled,
                    es.cadence_seconds,
                    es.freshness_slo_seconds,
                    lr.status AS latest_status,
                    lr.started_at AS latest_run_at
                FROM event_sources es
                LEFT JOIN latest_runs lr ON lr.source_name = es.source_name
                ORDER BY es.source_name ASC
                """
            )
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def validate_connectors_exist(session: AsyncSession, connectors: list[str]) -> list[str]:
        if not connectors:
            return []

        rows = await session.execute(
            text(
                """
                SELECT source_name
                FROM event_sources
                WHERE source_name = ANY(:connectors)
                """
            ),
            {"connectors": connectors},
        )
        existing = {str(row._mapping["source_name"]) for row in rows}
        missing = [name for name in connectors if name not in existing]
        return missing

    @staticmethod
    async def get_tenant_configuration(session: AsyncSession, tenant_id: str) -> dict:
        row = await session.execute(
            text(
                """
                SELECT
                    tenant_id,
                    anomaly_threshold,
                    enabled_connectors,
                    model_version,
                    rule_overrides_json,
                    version,
                    updated_at
                FROM tenant_configuration
                WHERE tenant_id = :tenant_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        item = row.first()
        if not item:
            await session.execute(
                text(
                    """
                    INSERT INTO tenant_configuration (
                        tenant_id,
                        anomaly_threshold,
                        enabled_connectors,
                        model_version,
                        rule_overrides_json,
                        version,
                        created_at,
                        updated_at
                    )
                    VALUES (:tenant_id, NULL, '[]'::jsonb, NULL, '{}'::jsonb, 1, NOW(), NOW())
                    ON CONFLICT (tenant_id) DO NOTHING
                    """
                ),
                {"tenant_id": tenant_id},
            )
            await session.commit()
            return await ControlRepository.get_tenant_configuration(session, tenant_id)

        mapping = dict(item._mapping)
        return {
            "tenant_id": str(mapping.get("tenant_id") or tenant_id),
            "anomaly_threshold": float(mapping["anomaly_threshold"]) if mapping.get("anomaly_threshold") is not None else None,
            "enabled_connectors": [str(entry) for entry in _to_list(mapping.get("enabled_connectors"))],
            "model_version": str(mapping.get("model_version")) if mapping.get("model_version") else None,
            "rule_overrides_json": _to_dict(mapping.get("rule_overrides_json")),
            "version": int(mapping.get("version") or 1),
            "updated_at": mapping.get("updated_at") or datetime.now(tz=UTC),
        }

    @staticmethod
    async def upsert_tenant_configuration(
        session: AsyncSession,
        *,
        tenant_id: str,
        anomaly_threshold: float | None,
        enabled_connectors: list[str],
        model_version: str | None,
        rule_overrides_json: dict[str, Any],
        expected_version: int | None,
    ) -> dict:
        existing = await ControlRepository.get_tenant_configuration(session, tenant_id)
        if expected_version is not None and existing["version"] != expected_version:
            raise RuntimeError(
                f"Configuration version mismatch. expected={expected_version} current={existing['version']}"
            )

        row = await session.execute(
            text(
                """
                INSERT INTO tenant_configuration (
                    tenant_id,
                    anomaly_threshold,
                    enabled_connectors,
                    model_version,
                    rule_overrides_json,
                    version,
                    created_at,
                    updated_at
                ) VALUES (
                    :tenant_id,
                    :anomaly_threshold,
                    CAST(:enabled_connectors AS jsonb),
                    :model_version,
                    CAST(:rule_overrides_json AS jsonb),
                    1,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (tenant_id)
                DO UPDATE SET
                    anomaly_threshold = EXCLUDED.anomaly_threshold,
                    enabled_connectors = EXCLUDED.enabled_connectors,
                    model_version = EXCLUDED.model_version,
                    rule_overrides_json = EXCLUDED.rule_overrides_json,
                    version = tenant_configuration.version + 1,
                    updated_at = NOW()
                RETURNING tenant_id, anomaly_threshold, enabled_connectors, model_version, rule_overrides_json, version, updated_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "anomaly_threshold": anomaly_threshold,
                "enabled_connectors": _json(enabled_connectors, default_obj="[]"),
                "model_version": model_version,
                "rule_overrides_json": _json(rule_overrides_json),
            },
        )
        await session.commit()

        mapping = dict(row.one()._mapping)
        return {
            "tenant_id": str(mapping.get("tenant_id") or tenant_id),
            "anomaly_threshold": float(mapping["anomaly_threshold"]) if mapping.get("anomaly_threshold") is not None else None,
            "enabled_connectors": [str(entry) for entry in _to_list(mapping.get("enabled_connectors"))],
            "model_version": str(mapping.get("model_version")) if mapping.get("model_version") else None,
            "rule_overrides_json": _to_dict(mapping.get("rule_overrides_json")),
            "version": int(mapping.get("version") or 1),
            "updated_at": mapping.get("updated_at") or datetime.now(tz=UTC),
        }

    @staticmethod
    async def set_global_connector_enabled(
        session: AsyncSession,
        *,
        source_name: str,
        enabled: bool,
    ) -> bool:
        exists = await session.execute(
            text("SELECT 1 FROM event_sources WHERE source_name = :source_name LIMIT 1"),
            {"source_name": source_name},
        )
        if exists.first() is None:
            await session.rollback()
            return False

        await session.execute(
            text(
                """
                UPDATE event_sources
                SET enabled = :enabled,
                    updated_at = NOW()
                WHERE source_name = :source_name
                """
            ),
            {"source_name": source_name, "enabled": enabled},
        )
        await session.execute(
            text(
                """
                INSERT INTO source_connector_state (source_name, enabled, next_run_at, updated_at)
                VALUES (:source_name, :enabled, CASE WHEN :enabled THEN NOW() ELSE NULL END, NOW())
                ON CONFLICT (source_name)
                DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    next_run_at = CASE WHEN EXCLUDED.enabled THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                """
            ),
            {"source_name": source_name, "enabled": enabled},
        )
        await session.commit()
        return True

    @staticmethod
    async def create_test_dataset(
        session: AsyncSession,
        *,
        tenant_id: str,
        name: str,
        source_type: str,
        events: list[dict[str, Any]],
        uploaded_by: str,
    ) -> dict:
        row = await session.execute(
            text(
                """
                INSERT INTO control_test_datasets (
                    tenant_id,
                    name,
                    source_type,
                    payload_json,
                    row_count,
                    uploaded_by,
                    created_at
                ) VALUES (
                    :tenant_id,
                    :name,
                    :source_type,
                    CAST(:payload_json AS jsonb),
                    :row_count,
                    :uploaded_by,
                    NOW()
                )
                RETURNING dataset_id, tenant_id, name, source_type, row_count, uploaded_by, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "name": name,
                "source_type": source_type,
                "payload_json": _json(events, default_obj="[]"),
                "row_count": len(events),
                "uploaded_by": uploaded_by,
            },
        )
        await session.commit()
        return dict(row.one()._mapping)

    @staticmethod
    async def fetch_test_dataset_events(session: AsyncSession, *, tenant_id: str, dataset_id: UUID) -> list[dict[str, Any]]:
        row = await session.execute(
            text(
                """
                SELECT payload_json
                FROM control_test_datasets
                WHERE tenant_id = :tenant_id
                  AND dataset_id = :dataset_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "dataset_id": str(dataset_id)},
        )
        item = row.first()
        if not item:
            raise ValueError("Dataset not found")
        return [entry for entry in _to_list(item._mapping.get("payload_json")) if isinstance(entry, dict)]

    @staticmethod
    async def create_test_run(
        session: AsyncSession,
        *,
        tenant_id: str,
        dataset_id: UUID | None,
        created_by: str,
    ) -> dict:
        row = await session.execute(
            text(
                """
                INSERT INTO control_test_runs (
                    tenant_id,
                    dataset_id,
                    status,
                    created_by,
                    started_at,
                    created_at,
                    summary_json
                ) VALUES (
                    :tenant_id,
                    :dataset_id,
                    'running',
                    :created_by,
                    NOW(),
                    NOW(),
                    '{}'::jsonb
                )
                RETURNING run_id, tenant_id, dataset_id, status, created_by, started_at, finished_at, summary_json, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "dataset_id": str(dataset_id) if dataset_id else None,
                "created_by": created_by,
            },
        )
        await session.commit()
        return dict(row.one()._mapping)

    @staticmethod
    async def append_test_run_result(
        session: AsyncSession,
        *,
        run_id: UUID,
        event_id: UUID | None,
        ingest_status: str | None,
        queued: bool | None,
        decision_found: bool,
        risk_level: str | None,
        risk_score: float | None,
        alert_found: bool,
        details: dict[str, Any],
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO control_test_run_results (
                    run_id,
                    event_id,
                    ingest_status,
                    queued,
                    decision_found,
                    risk_level,
                    risk_score,
                    alert_found,
                    details,
                    created_at
                ) VALUES (
                    :run_id,
                    :event_id,
                    :ingest_status,
                    :queued,
                    :decision_found,
                    :risk_level,
                    :risk_score,
                    :alert_found,
                    CAST(:details AS jsonb),
                    NOW()
                )
                """
            ),
            {
                "run_id": str(run_id),
                "event_id": str(event_id) if event_id else None,
                "ingest_status": ingest_status,
                "queued": queued,
                "decision_found": decision_found,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "alert_found": alert_found,
                "details": _json(details),
            },
        )
        await session.commit()

    @staticmethod
    async def complete_test_run(
        session: AsyncSession,
        *,
        run_id: UUID,
        status: str,
        summary_json: dict[str, Any],
    ) -> dict:
        row = await session.execute(
            text(
                """
                UPDATE control_test_runs
                SET status = :status,
                    finished_at = NOW(),
                    summary_json = CAST(:summary_json AS jsonb)
                WHERE run_id = :run_id
                RETURNING run_id, tenant_id, dataset_id, status, created_by, started_at, finished_at, summary_json, created_at
                """
            ),
            {
                "run_id": str(run_id),
                "status": status,
                "summary_json": _json(summary_json),
            },
        )
        await session.commit()
        return dict(row.one()._mapping)

    @staticmethod
    async def list_test_runs(session: AsyncSession, *, tenant_id: str, limit: int) -> list[dict]:
        rows = await session.execute(
            text(
                """
                SELECT run_id, tenant_id, dataset_id, status, created_by, started_at, finished_at, summary_json, created_at
                FROM control_test_runs
                WHERE tenant_id = :tenant_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "limit": limit},
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def get_test_run(session: AsyncSession, *, tenant_id: str, run_id: UUID) -> dict | None:
        row = await session.execute(
            text(
                """
                SELECT run_id, tenant_id, dataset_id, status, created_by, started_at, finished_at, summary_json, created_at
                FROM control_test_runs
                WHERE tenant_id = :tenant_id AND run_id = :run_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "run_id": str(run_id)},
        )
        item = row.first()
        return dict(item._mapping) if item else None

    @staticmethod
    async def list_test_run_results(session: AsyncSession, *, run_id: UUID) -> list[dict]:
        rows = await session.execute(
            text(
                """
                SELECT event_id, ingest_status, queued, decision_found, risk_level, risk_score, alert_found, details, created_at
                FROM control_test_run_results
                WHERE run_id = :run_id
                ORDER BY id ASC
                """
            ),
            {"run_id": str(run_id)},
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def fetch_decision_and_alert(
        session: AsyncSession,
        *,
        tenant_id: str,
        event_id: UUID,
    ) -> tuple[dict | None, dict | None]:
        await set_tenant_context(session, tenant_id)

        decision_row = await session.execute(
            text(
                """
                SELECT risk_level, risk_score
                FROM risk_decisions
                WHERE tenant_id = :tenant_id AND event_id = :event_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": str(event_id)},
        )
        decision_item = decision_row.first()

        alert_row = await session.execute(
            text(
                """
                SELECT alert_id, state
                FROM alerts_v2
                WHERE tenant_id = :tenant_id AND event_id = :event_id
                ORDER BY opened_at DESC
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": str(event_id)},
        )
        alert_item = alert_row.first()
        return (
            dict(decision_item._mapping) if decision_item else None,
            dict(alert_item._mapping) if alert_item else None,
        )

    @staticmethod
    async def list_alert_destinations(session: AsyncSession, *, tenant_id: str) -> list[dict]:
        rows = await session.execute(
            text(
                """
                SELECT destination_id, tenant_id, channel, name, enabled, config_json, verification_status, last_tested_at, updated_at
                FROM control_alert_destinations
                WHERE tenant_id = :tenant_id
                ORDER BY created_at DESC
                """
            ),
            {"tenant_id": tenant_id},
        )
        results: list[dict] = []
        for row in rows:
            item = dict(row._mapping)
            item["config"] = _to_dict(item.pop("config_json", {}))
            results.append(item)
        return results

    @staticmethod
    async def get_alert_destination(session: AsyncSession, *, tenant_id: str, destination_id: UUID) -> dict | None:
        row = await session.execute(
            text(
                """
                SELECT destination_id, tenant_id, channel, name, enabled, config_json, verification_status, last_tested_at, updated_at
                FROM control_alert_destinations
                WHERE tenant_id = :tenant_id
                  AND destination_id = :destination_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "destination_id": str(destination_id)},
        )
        item = row.first()
        if not item:
            return None
        result = dict(item._mapping)
        result["config"] = _to_dict(result.pop("config_json", {}))
        return result

    @staticmethod
    async def create_alert_destination(
        session: AsyncSession,
        *,
        tenant_id: str,
        channel: str,
        name: str,
        enabled: bool,
        config: dict[str, Any],
        actor: str,
    ) -> dict:
        row = await session.execute(
            text(
                """
                INSERT INTO control_alert_destinations (
                    tenant_id,
                    channel,
                    name,
                    enabled,
                    config_json,
                    verification_status,
                    created_by,
                    updated_by,
                    created_at,
                    updated_at
                ) VALUES (
                    :tenant_id,
                    :channel,
                    :name,
                    :enabled,
                    CAST(:config_json AS jsonb),
                    'pending',
                    :actor,
                    :actor,
                    NOW(),
                    NOW()
                )
                RETURNING destination_id, tenant_id, channel, name, enabled, config_json, verification_status, last_tested_at, updated_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "channel": channel,
                "name": name,
                "enabled": enabled,
                "config_json": _json(config),
                "actor": actor,
            },
        )
        await session.commit()
        item = dict(row.one()._mapping)
        item["config"] = _to_dict(item.pop("config_json", {}))
        return item

    @staticmethod
    async def update_alert_destination(
        session: AsyncSession,
        *,
        tenant_id: str,
        destination_id: UUID,
        name: str | None,
        enabled: bool | None,
        config: dict[str, Any] | None,
        actor: str,
    ) -> dict | None:
        existing = await ControlRepository.get_alert_destination(
            session,
            tenant_id=tenant_id,
            destination_id=destination_id,
        )
        if not existing:
            return None

        await session.execute(
            text(
                """
                UPDATE control_alert_destinations
                SET name = COALESCE(:name, name),
                    enabled = COALESCE(:enabled, enabled),
                    config_json = COALESCE(CAST(:config_json AS jsonb), config_json),
                    updated_by = :actor,
                    updated_at = NOW()
                WHERE tenant_id = :tenant_id
                  AND destination_id = :destination_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "destination_id": str(destination_id),
                "name": name,
                "enabled": enabled,
                "config_json": _json(config) if config is not None else None,
                "actor": actor,
            },
        )
        await session.commit()
        return await ControlRepository.get_alert_destination(session, tenant_id=tenant_id, destination_id=destination_id)

    @staticmethod
    async def delete_alert_destination(session: AsyncSession, *, tenant_id: str, destination_id: UUID) -> bool:
        result = await session.execute(
            text(
                """
                DELETE FROM control_alert_destinations
                WHERE tenant_id = :tenant_id
                  AND destination_id = :destination_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "destination_id": str(destination_id),
            },
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def mark_destination_verification(
        session: AsyncSession,
        *,
        tenant_id: str,
        destination_id: UUID,
        status: str,
        actor: str,
    ) -> dict | None:
        await session.execute(
            text(
                """
                UPDATE control_alert_destinations
                SET verification_status = :status,
                    last_tested_at = NOW(),
                    updated_by = :actor,
                    updated_at = NOW()
                WHERE tenant_id = :tenant_id
                  AND destination_id = :destination_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "destination_id": str(destination_id),
                "status": status,
                "actor": actor,
            },
        )
        await session.commit()
        return await ControlRepository.get_alert_destination(session, tenant_id=tenant_id, destination_id=destination_id)

    @staticmethod
    async def get_alert_routing_policy(session: AsyncSession, *, tenant_id: str) -> dict:
        row = await session.execute(
            text(
                """
                SELECT tenant_id, policy_json, updated_by, updated_at
                FROM control_alert_routing_policy
                WHERE tenant_id = :tenant_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        item = row.first()
        if not item:
            await session.execute(
                text(
                    """
                    INSERT INTO control_alert_routing_policy (tenant_id, policy_json, updated_by, updated_at)
                    VALUES (:tenant_id, '{}'::jsonb, 'system', NOW())
                    ON CONFLICT (tenant_id) DO NOTHING
                    """
                ),
                {"tenant_id": tenant_id},
            )
            await session.commit()
            return await ControlRepository.get_alert_routing_policy(session, tenant_id=tenant_id)

        mapping = dict(item._mapping)
        return {
            "tenant_id": str(mapping.get("tenant_id") or tenant_id),
            "policy_json": _to_dict(mapping.get("policy_json")),
            "updated_by": str(mapping.get("updated_by")) if mapping.get("updated_by") else None,
            "updated_at": mapping.get("updated_at") or datetime.now(tz=UTC),
        }

    @staticmethod
    async def upsert_alert_routing_policy(
        session: AsyncSession,
        *,
        tenant_id: str,
        policy_json: dict[str, Any],
        actor: str,
    ) -> dict:
        row = await session.execute(
            text(
                """
                INSERT INTO control_alert_routing_policy (tenant_id, policy_json, updated_by, updated_at)
                VALUES (:tenant_id, CAST(:policy_json AS jsonb), :actor, NOW())
                ON CONFLICT (tenant_id)
                DO UPDATE SET
                    policy_json = EXCLUDED.policy_json,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                RETURNING tenant_id, policy_json, updated_by, updated_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "policy_json": _json(policy_json),
                "actor": actor,
            },
        )
        await session.commit()
        mapping = dict(row.one()._mapping)
        return {
            "tenant_id": str(mapping.get("tenant_id") or tenant_id),
            "policy_json": _to_dict(mapping.get("policy_json")),
            "updated_by": str(mapping.get("updated_by")) if mapping.get("updated_by") else None,
            "updated_at": mapping.get("updated_at") or datetime.now(tz=UTC),
        }

    @staticmethod
    async def create_delivery_log(
        session: AsyncSession,
        *,
        tenant_id: str,
        destination_id: UUID | None,
        channel: str,
        alert_key: str,
        event_id: UUID | None,
        status: str,
        attempt_no: int,
        response_code: int | None,
        response_body: str | None,
        error_message: str | None,
        payload_json: dict[str, Any],
        is_test: bool,
        delivered: bool,
    ) -> dict:
        row = await session.execute(
            text(
                """
                INSERT INTO control_alert_delivery_logs (
                    tenant_id,
                    destination_id,
                    channel,
                    alert_key,
                    event_id,
                    status,
                    attempt_no,
                    response_code,
                    response_body,
                    error_message,
                    payload_json,
                    is_test,
                    attempted_at,
                    delivered_at
                ) VALUES (
                    :tenant_id,
                    :destination_id,
                    :channel,
                    :alert_key,
                    :event_id,
                    :status,
                    :attempt_no,
                    :response_code,
                    :response_body,
                    :error_message,
                    CAST(:payload_json AS jsonb),
                    :is_test,
                    NOW(),
                    CASE WHEN :delivered THEN NOW() ELSE NULL END
                )
                RETURNING delivery_id, tenant_id, destination_id, channel, alert_key, event_id, status, attempt_no,
                          response_code, error_message, payload_json, is_test, attempted_at, delivered_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "destination_id": str(destination_id) if destination_id else None,
                "channel": channel,
                "alert_key": alert_key,
                "event_id": str(event_id) if event_id else None,
                "status": status,
                "attempt_no": attempt_no,
                "response_code": response_code,
                "response_body": response_body,
                "error_message": error_message,
                "payload_json": _json(payload_json),
                "is_test": is_test,
                "delivered": delivered,
            },
        )
        await session.commit()
        mapping = dict(row.one()._mapping)
        mapping["payload_json"] = _to_dict(mapping.get("payload_json"))
        return mapping

    @staticmethod
    async def list_delivery_logs(session: AsyncSession, *, tenant_id: str | None, limit: int) -> list[dict]:
        where = ""
        params: dict[str, Any] = {"limit": limit}
        if tenant_id:
            where = "WHERE tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        rows = await session.execute(
            text(
                f"""
                SELECT delivery_id, tenant_id, destination_id, channel, alert_key, event_id, status, attempt_no,
                       response_code, error_message, payload_json, is_test, attempted_at, delivered_at
                FROM control_alert_delivery_logs
                {where}
                ORDER BY attempted_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        results: list[dict] = []
        for row in rows:
            item = dict(row._mapping)
            item["payload_json"] = _to_dict(item.get("payload_json"))
            results.append(item)
        return results

    @staticmethod
    async def reconciliation_ingestion_summary(
        session: AsyncSession,
        *,
        tenant_id: str,
        from_ts: datetime,
        to_ts: datetime,
    ) -> dict:
        await set_tenant_context(session, tenant_id)

        ingested = await session.execute(
            text(
                """
                SELECT COUNT(*) AS count
                FROM events_v2
                WHERE tenant_id = :tenant_id
                  AND ingested_at >= :from_ts
                  AND ingested_at <= :to_ts
                """
            ),
            {"tenant_id": tenant_id, "from_ts": from_ts, "to_ts": to_ts},
        )
        processed = await session.execute(
            text(
                """
                SELECT COUNT(*) AS count
                FROM risk_decisions
                WHERE tenant_id = :tenant_id
                  AND created_at >= :from_ts
                  AND created_at <= :to_ts
                """
            ),
            {"tenant_id": tenant_id, "from_ts": from_ts, "to_ts": to_ts},
        )
        raised = await session.execute(
            text(
                """
                SELECT COUNT(*) AS count
                FROM alerts_v2
                WHERE tenant_id = :tenant_id
                  AND opened_at >= :from_ts
                  AND opened_at <= :to_ts
                """
            ),
            {"tenant_id": tenant_id, "from_ts": from_ts, "to_ts": to_ts},
        )

        return {
            "ingested_events": int(ingested.scalar_one() or 0),
            "processed_decisions": int(processed.scalar_one() or 0),
            "raised_alerts": int(raised.scalar_one() or 0),
        }

    @staticmethod
    async def reconciliation_delivery_summary(
        session: AsyncSession,
        *,
        tenant_id: str,
        from_ts: datetime,
        to_ts: datetime,
    ) -> dict:
        delivered = await session.execute(
            text(
                """
                SELECT COUNT(*) AS delivered
                FROM control_alert_delivery_logs
                WHERE tenant_id = :tenant_id
                  AND attempted_at >= :from_ts
                  AND attempted_at <= :to_ts
                  AND status = 'delivered'
                """
            ),
            {"tenant_id": tenant_id, "from_ts": from_ts, "to_ts": to_ts},
        )
        failed = await session.execute(
            text(
                """
                SELECT COUNT(*) AS failed
                FROM control_alert_delivery_logs
                WHERE tenant_id = :tenant_id
                  AND attempted_at >= :from_ts
                  AND attempted_at <= :to_ts
                  AND status != 'delivered'
                """
            ),
            {"tenant_id": tenant_id, "from_ts": from_ts, "to_ts": to_ts},
        )
        return {
            "delivered_alerts": int(delivered.scalar_one() or 0),
            "failed_deliveries": int(failed.scalar_one() or 0),
        }

    @staticmethod
    async def write_config_audit(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        before_json: dict[str, Any],
        after_json: dict[str, Any],
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO control_config_audit_log (
                    tenant_id,
                    actor,
                    action,
                    resource_type,
                    resource_id,
                    before_json,
                    after_json,
                    created_at
                ) VALUES (
                    :tenant_id,
                    :actor,
                    :action,
                    :resource_type,
                    :resource_id,
                    CAST(:before_json AS jsonb),
                    CAST(:after_json AS jsonb),
                    NOW()
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "before_json": _json(before_json),
                "after_json": _json(after_json),
            },
        )
        await session.commit()

    @staticmethod
    async def list_config_audit(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        limit: int,
    ) -> list[dict]:
        where = ""
        params: dict[str, Any] = {"limit": limit}
        if tenant_id:
            where = "WHERE tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        rows = await session.execute(
            text(
                f"""
                SELECT id, tenant_id, actor, action, resource_type, resource_id, before_json, after_json, created_at
                FROM control_config_audit_log
                {where}
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        results: list[dict] = []
        for row in rows:
            item = dict(row._mapping)
            item["before_json"] = _to_dict(item.get("before_json"))
            item["after_json"] = _to_dict(item.get("after_json"))
            results.append(item)
        return results
