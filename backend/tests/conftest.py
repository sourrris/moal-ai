"""Test suite conftest — clear service-specific 'app' module caches between files.

Multiple backend services share the top-level package name ``app`` (risk/api,
risk/alert_router, risk/connector, risk/worker).  When pytest collects test
files in alphabetical order, the first file to do ``import app`` wins and
populates ``sys.modules["app"]``.  Every subsequent file that needs a
*different* ``app`` then imports the wrong package, causing collection
failures.

The ``pytest_collect_file`` hook runs just before pytest imports a test file,
so purging stale ``app.*`` entries here gives each file a clean slate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def pytest_collect_file(parent: pytest.Collector, file_path: Path) -> pytest.Collector | None:  # noqa: ARG001
    """Purge stale ``app.*`` module entries before each test file is imported."""
    stale = [key for key in sys.modules if key == "app" or key.startswith("app.")]
    for key in stale:
        del sys.modules[key]
    return None
