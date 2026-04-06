"""Shared package for cross-service utilities."""

from .config import BaseServiceSettings
from .logging import configure_logging

__all__ = ["BaseServiceSettings", "configure_logging"]
