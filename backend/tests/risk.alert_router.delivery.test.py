"""Alert router delivery tests: HMAC signatures, SMTP TLS, dedup, and tenant checks."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "libs" / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "risk" / "alert_router"))

from app.application.router import AlertRouter, _deliver_to_destination
from app.config import get_settings

settings = get_settings()

_SIGNING_SECRET = "test-signing-secret-for-hmac-verification"
_TENANT = "tenant-a"


def _alert_payload(tenant_id: str = _TENANT) -> dict:
    return {
        "alert_id": str(uuid4()),
        "event_id": str(uuid4()),
        "tenant_id": tenant_id,
        "severity": "high",
        "risk_score": 0.92,
        "reasons": ["ml_threshold_breach"],
    }


class _FakeHttpxResponse:
    def __init__(self, status_code: int = 200, text: str = "ok"):
        self.status_code = status_code
        self.text = text


class _FakeHttpxClient:
    def __init__(self, response: _FakeHttpxResponse):
        self._response = response
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def post(self, url, *, content=None, headers=None, json=None, **kwargs):
        self.requests.append({"url": url, "content": content, "headers": headers or {}})
        return self._response


class _FakeSMTP:
    def __init__(self, *, host, port, timeout):
        self.host = host
        self.port = port
        self.starttls_called = False
        self.login_called = False
        self.login_args: tuple = ()
        self.sent: list = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.login_called = True
        self.login_args = (user, password)

    def send_message(self, message):
        self.sent.append(message)


class _FakeMessage:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode()
        self.acked = False

    async def ack(self):
        self.acked = True


class _FakeRow:
    def __init__(self, mapping: dict):
        self._mapping = mapping


class _FakeResult:
    def __init__(self, rows: list[dict] | None = None, single: dict | None = None):
        self._rows = [_FakeRow(r) for r in (rows or [])]
        self._single = _FakeRow(single) if single else None

    def __iter__(self):
        return iter(self._rows)

    def first(self):
        return self._single


class _FakeSessionCtx:
    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *_):
        pass


@pytest.mark.asyncio
async def test_webhook_delivery_includes_correct_hmac_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "alert_router_webhook_signing_secret", _SIGNING_SECRET)
    monkeypatch.setattr(settings, "alert_router_timeout_seconds", 10)

    payload = _alert_payload()
    fake_client = _FakeHttpxClient(_FakeHttpxResponse(200))

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: fake_client)

    destination = {"channel": "webhook", "config_json": {"url": "http://example.com/hook"}}
    status, code, _, error = await _deliver_to_destination(destination, payload)

    assert status == "delivered"
    assert error is None
    assert len(fake_client.requests) == 1

    req = fake_client.requests[0]
    sent_sig = req["headers"].get("X-Aegis-Signature", "")
    assert sent_sig.startswith("sha256=")

    body_bytes = req["content"]
    expected_sig = "sha256=" + hmac.new(
        _SIGNING_SECRET.encode(),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    assert sent_sig == expected_sig


@pytest.mark.asyncio
async def test_webhook_delivery_returns_failed_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "alert_router_webhook_signing_secret", _SIGNING_SECRET)
    monkeypatch.setattr(settings, "alert_router_timeout_seconds", 10)

    fake_client = _FakeHttpxClient(_FakeHttpxResponse(500, "server error"))

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: fake_client)

    destination = {"channel": "webhook", "config_json": {"url": "http://example.com/hook"}}
    status, code, _, error = await _deliver_to_destination(destination, _alert_payload())

    assert status == "failed"
    assert code == 500


@pytest.mark.asyncio
async def test_email_delivery_uses_starttls_and_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "alert_router_email_smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "alert_router_email_smtp_port", 587)
    monkeypatch.setattr(settings, "alert_router_email_smtp_username", "user@test")
    monkeypatch.setattr(settings, "alert_router_email_smtp_password", "secret")
    monkeypatch.setattr(settings, "alert_router_email_smtp_tls", True)
    monkeypatch.setattr(settings, "alert_router_email_from", "no-reply@test")

    smtp_instance = _FakeSMTP(host="smtp.test", port=587, timeout=10)

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", lambda host, port, timeout: smtp_instance)

    destination = {
        "channel": "email",
        "config_json": {"to": ["analyst@test.com"], "subject": "Alert"},
    }
    status, _, _, error = await _deliver_to_destination(destination, _alert_payload())

    assert status == "delivered"
    assert error is None
    assert smtp_instance.starttls_called
    assert smtp_instance.login_called
    assert smtp_instance.login_args == ("user@test", "secret")
    assert len(smtp_instance.sent) == 1


@pytest.mark.asyncio
async def test_email_delivery_fails_on_missing_recipient() -> None:
    destination = {"channel": "email", "config_json": {}}
    status, _, _, error = await _deliver_to_destination(destination, _alert_payload())

    assert status == "failed"
    assert "recipient" in (error or "").lower()


@pytest.mark.asyncio
async def test_on_alert_acks_without_processing_when_tenant_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.router as router_mod

    db_queries: list = []

    class _FakeSession:
        async def execute(self, stmt, params=None):
            db_queries.append(str(stmt))
            return _FakeResult()

        async def commit(self):
            pass

    monkeypatch.setattr(router_mod, "SessionLocal", lambda: _FakeSessionCtx(_FakeSession()))

    router = AlertRouter(rabbit_channel=SimpleNamespace())
    payload_no_tenant = {"alert_id": str(uuid4()), "severity": "high"}
    message = _FakeMessage(payload_no_tenant)
    await router._on_alert(message)

    assert message.acked
    assert len(db_queries) == 0


@pytest.mark.asyncio
async def test_on_alert_skips_already_delivered_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.router as router_mod

    dest_id = uuid4()
    alert_id = str(uuid4())
    delivery_calls: list = []

    class _FakeSession:
        def __init__(self):
            self._call_count = 0

        async def execute(self, stmt, params=None):
            sql = str(stmt)
            self._call_count += 1
            if "control_alert_destinations" in sql:
                return _FakeResult(rows=[{
                    "destination_id": dest_id,
                    "tenant_id": _TENANT,
                    "channel": "webhook",
                    "enabled": True,
                    "config_json": {"url": "http://example.com/hook"},
                }])
            if "control_alert_routing_policy" in sql:
                return _FakeResult()
            if "control_alert_delivery_logs" in sql and "status = 'delivered'" in sql:
                return _FakeResult(single={"exists": 1})
            return _FakeResult()

        async def commit(self):
            pass

    monkeypatch.setattr(router_mod, "SessionLocal", lambda: _FakeSessionCtx(_FakeSession()))

    async def fake_deliver(destination, payload):
        delivery_calls.append(destination)
        return "delivered", 200, "ok", None

    monkeypatch.setattr(router_mod, "_deliver_to_destination", fake_deliver)

    router = AlertRouter(rabbit_channel=SimpleNamespace())
    payload = {**_alert_payload(), "alert_id": alert_id}
    message = _FakeMessage(payload)
    await router._on_alert(message)

    assert message.acked
    assert len(delivery_calls) == 0
