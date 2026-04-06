"""Compatibility shim for the connector registry surface."""

from moal_common.connector_abstractions import (
    connector_registry,
    load_connector_from_config,
    register_connector,
)

__all__ = ["connector_registry", "register_connector", "load_connector_from_config"]

