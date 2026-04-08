"""Test suite conftest — clear stale 'app' module caches between test files.

The API service uses the top-level package name ``app``.  When pytest collects
test files in alphabetical order, the first file to do ``import app`` wins and
populates ``sys.modules["app"]``.  Every subsequent file that needs a
*different* ``app`` import path then gets the wrong package, causing collection
failures.

``pytest_collect_file`` returns a custom ``IsolatedModule`` collector for
each test file.  Its ``collect()`` method purges stale ``app.*`` entries from
``sys.modules`` *before* the file is imported, giving each file a clean slate.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from _pytest.python import Module


class IsolatedModule(Module):
    """Module collector that purges stale ``app.*`` entries before importing."""

    def collect(self) -> Iterator:  # type: ignore[override]
        stale = [k for k in sys.modules if k == "app" or k.startswith("app.")]
        for k in stale:
            del sys.modules[k]
        yield from super().collect()


def pytest_collect_file(parent: pytest.Collector, file_path: Path) -> pytest.Collector | None:
    """Return an IsolatedModule collector for test files."""
    if file_path.suffix == ".py" and (
        file_path.name.startswith("test_") or file_path.name.endswith(".test.py")
    ):
        return IsolatedModule.from_parent(parent, path=file_path)
    return None
