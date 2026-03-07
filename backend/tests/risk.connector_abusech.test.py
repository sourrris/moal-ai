"""Regression coverage for the abuse.ch reference connector."""

import importlib
import importlib.util
import sys
import types
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "common"))
sys.path.insert(0, str(ROOT.parent / "aegis-connectors" / "python"))

CONNECTOR_APP_ROOT = ROOT / "services" / "risk" / "connector" / "app"


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


app_package = types.ModuleType("app")
app_package.__path__ = [str(CONNECTOR_APP_ROOT)]
sys.modules["app"] = app_package

application_package = types.ModuleType("app.application")
application_package.__path__ = [str(CONNECTOR_APP_ROOT / "application")]
sys.modules["app.application"] = application_package

_load_module("app.config", CONNECTOR_APP_ROOT / "config.py")
_load_module("app.application.connectors", CONNECTOR_APP_ROOT / "application" / "connectors.py")

reference_plugins = importlib.import_module("aegis_connectors.reference_plugins")


@pytest.mark.asyncio
async def test_abusech_connector_parses_plain_text_feodo_blocklist(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
        return httpx.Response(
            200,
            text="# comment\n45.61.136.0\n87.120.84.0\n45.61.136.0\n",
            headers={"content-type": "text/plain; charset=utf-8"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(reference_plugins, "request_with_retry", fake_request_with_retry)

    result = await reference_plugins.AbuseChIPConnector().fetch()

    assert result.status == "success"
    assert result.fetched_records == 2
    assert result.upserted_records == 2
    assert [item["ip"] for item in result.ip_records] == ["45.61.136.0", "87.120.84.0"]
    assert result.ip_records[0]["raw"]["status"] == "listed"
    assert "feodotracker.abuse.ch" in result.details["source_feed"]


@pytest.mark.asyncio
async def test_fatf_connector_uses_current_fallback_snapshot_when_site_blocks_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def blocked_request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
        request = httpx.Request(method, url)
        response = httpx.Response(403, request=request, text="blocked")
        raise httpx.HTTPStatusError("blocked", request=request, response=response)

    monkeypatch.setattr(reference_plugins, "request_with_retry", blocked_request_with_retry)

    result = await reference_plugins.FatfConnector().fetch()

    assert result.status == "success"
    assert result.version == "20260213"
    assert result.details["source"] == "fatf-fallback"
    assert result.jurisdiction_scores["IR"] == 0.95
    assert result.jurisdiction_scores["MM"] == 0.95
    assert result.jurisdiction_scores["BG"] == 0.8
