from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class TenantProcessingConfig:
    tenant_id: str
    anomaly_threshold: float | None
    enabled_connectors: list[str]
    model_version: str | None
    rule_overrides: dict


class TenantConfigRepository:
    @staticmethod
    async def fetch(session: AsyncSession, tenant_id: str) -> TenantProcessingConfig | None:
        row = await session.execute(
            text(
                """
                SELECT tenant_id, anomaly_threshold, enabled_connectors, model_version, rule_overrides_json
                FROM tenant_configuration
                WHERE tenant_id = :tenant_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        item = row.first()
        if not item:
            return None

        mapping = dict(item._mapping)

        enabled_connectors_raw = mapping.get("enabled_connectors")
        if isinstance(enabled_connectors_raw, str):
            try:
                enabled_connectors = json.loads(enabled_connectors_raw)
            except json.JSONDecodeError:
                enabled_connectors = []
        elif isinstance(enabled_connectors_raw, list):
            enabled_connectors = enabled_connectors_raw
        else:
            enabled_connectors = []

        rule_overrides_raw = mapping.get("rule_overrides_json")
        if isinstance(rule_overrides_raw, str):
            try:
                rule_overrides = json.loads(rule_overrides_raw)
            except json.JSONDecodeError:
                rule_overrides = {}
        elif isinstance(rule_overrides_raw, dict):
            rule_overrides = rule_overrides_raw
        else:
            rule_overrides = {}

        return TenantProcessingConfig(
            tenant_id=str(mapping.get("tenant_id") or tenant_id),
            anomaly_threshold=float(mapping["anomaly_threshold"]) if mapping.get("anomaly_threshold") is not None else None,
            enabled_connectors=[str(item) for item in enabled_connectors if isinstance(item, str)],
            model_version=str(mapping.get("model_version")) if mapping.get("model_version") else None,
            rule_overrides=rule_overrides,
        )
