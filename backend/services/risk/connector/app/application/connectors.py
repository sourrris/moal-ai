from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ConnectorResult:
    source_name: str
    status: str
    fetched_records: int
    upserted_records: int
    checksum: str
    version: str
    details: dict = field(default_factory=dict)
    cursor_state: dict = field(default_factory=dict)
    sanctions_names: list[str] = field(default_factory=list)
    pep_names: list[str] = field(default_factory=list)
    jurisdiction_scores: dict[str, float] = field(default_factory=dict)
    fx_rates: dict[str, float] = field(default_factory=dict)
    fx_rate_date: date | None = None
    ip_records: list[dict] = field(default_factory=list)
    bin_records: list[dict] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)


class BaseConnector:
    source_name: str
    config_enabled: bool = True

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:  # pragma: no cover - interface
        raise NotImplementedError


_REFERENCE_CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {}


def register_reference_connector(connector_cls: type[BaseConnector]) -> type[BaseConnector]:
    source_name = connector_cls.source_name
    if not source_name:
        raise ValueError("Connector source_name is required")
    _REFERENCE_CONNECTOR_REGISTRY[source_name] = connector_cls
    return connector_cls


def _discover_plugin_python_path() -> Path | None:
    """Find `aegis-connectors/python` by walking upward from this module."""
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        candidate = parent / "aegis-connectors" / "python"
        if candidate.exists():
            return candidate
    return None


def load_reference_plugins(module_paths: str | None) -> list[str]:
    if not module_paths:
        return []

    plugin_python_path = _discover_plugin_python_path()
    if plugin_python_path is not None:
        candidate = str(plugin_python_path)
        if candidate not in sys.path:
            sys.path.append(candidate)

    loaded: list[str] = []
    for item in module_paths.split(","):
        module_path = item.strip()
        if not module_path:
            continue
        try:
            importlib.import_module(module_path)
            loaded.append(module_path)
        except ModuleNotFoundError:
            logger.warning("connector_plugin_module_missing", extra={"plugin_module": module_path})
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "connector_plugin_module_load_failed",
                extra={"plugin_module": module_path, "error": str(exc)},
            )
    return loaded


def default_connectors() -> list[BaseConnector]:
    load_reference_plugins(settings.connector_reference_modules)
    connectors: list[BaseConnector] = []
    for connector_cls in _REFERENCE_CONNECTOR_REGISTRY.values():
        connector = connector_cls()
        if connector.config_enabled:
            connectors.append(connector)
    return sorted(connectors, key=lambda item: item.source_name)


def degraded_result(source_name: str, reason: str) -> ConnectorResult:
    now = datetime.now(tz=UTC).isoformat()
    return ConnectorResult(
        source_name=source_name,
        status="degraded",
        fetched_records=0,
        upserted_records=0,
        checksum="",
        version=now,
        details={"reason": reason},
    )


__all__ = [
    "BaseConnector",
    "ConnectorResult",
    "register_reference_connector",
    "default_connectors",
    "degraded_result",
    "load_reference_plugins",
]
