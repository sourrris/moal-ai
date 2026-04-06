from __future__ import annotations

import importlib
import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock
from typing import Any

from moal_common.platform_schema import StandardizedTransaction

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    @abstractmethod
    def verify(self, payload: dict[str, Any]) -> None:
        """Validate connector-specific payload shape, raising ValueError on invalid input."""

    @abstractmethod
    def normalize(self, payload: dict[str, Any], *, tenant_id: str) -> StandardizedTransaction:
        """Map connector payload into canonical StandardizedTransaction."""

    @abstractmethod
    def get_source_name(self) -> str:
        """Return stable connector source identifier."""

    @abstractmethod
    async def healthcheck(self) -> dict[str, Any]:
        """Return connector health status metadata for diagnostics."""


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, type[BaseConnector]] = {}
        self._lock = Lock()

    def register(self, connector_cls: type[BaseConnector]) -> type[BaseConnector]:
        source_name = connector_cls().get_source_name()
        with self._lock:
            if source_name in self._connectors:
                raise ValueError(f"Connector already registered for source: {source_name}")
            self._connectors[source_name] = connector_cls
        return connector_cls

    def get(self, source_name: str) -> BaseConnector | None:
        connector_cls = self._connectors.get(source_name)
        if connector_cls is None:
            return None
        return connector_cls()

    def list_sources(self) -> list[str]:
        return sorted(self._connectors)

    def autoload_modules(self, module_paths: list[str]) -> list[str]:
        loaded: list[str] = []
        for module_path in module_paths:
            candidate = module_path.strip()
            if not candidate:
                continue
            try:
                importlib.import_module(candidate)
                loaded.append(candidate)
            except ModuleNotFoundError:
                logger.warning("ingest_connector_module_missing", extra={"plugin_module": candidate})
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ingest_connector_module_load_failed",
                    extra={"plugin_module": candidate, "error": str(exc)},
                )
        return loaded


connector_registry = ConnectorRegistry()


def register_connector(connector_cls: type[BaseConnector]) -> type[BaseConnector]:
    return connector_registry.register(connector_cls)


def _discover_plugin_python_path() -> Path | None:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        candidate = parent / "aegis-connectors" / "python"
        if candidate.exists():
            return candidate
    return None


def load_connector_from_config(module_paths: str | None) -> list[str]:
    if not module_paths:
        return []

    plugin_python_path = _discover_plugin_python_path()
    if plugin_python_path is not None:
        candidate = str(plugin_python_path)
        if candidate not in sys.path:
            sys.path.append(candidate)

    return connector_registry.autoload_modules(module_paths.split(","))


__all__ = ["BaseConnector", "ConnectorRegistry", "connector_registry", "register_connector", "load_connector_from_config"]
