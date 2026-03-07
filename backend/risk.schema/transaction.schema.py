"""Compatibility shim for standardized risk platform schemas.

Canonical implementations live in `risk_common.platform_schema`.
"""

from risk_common.platform_schema import StandardizedAlert, StandardizedTransaction

__all__ = ["StandardizedTransaction", "StandardizedAlert"]

