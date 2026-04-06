"""Compatibility shim for standardized risk platform schemas.

Canonical implementations live in `moal_common.platform_schema`.
"""

from moal_common.platform_schema import StandardizedAlert, StandardizedTransaction

__all__ = ["StandardizedTransaction", "StandardizedAlert"]

