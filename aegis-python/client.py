from __future__ import annotations

from typing import Any, Callable

import requests

from .models import EventIngestResult, PlatformConfig


class AegisClient:
    def __init__(self, base_url: str, get_jwt: Callable[[], str | None], timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._get_jwt = get_jwt
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = self._get_jwt()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def ingest(self, payload: dict[str, Any]) -> EventIngestResult:
        response = requests.post(
            f"{self._base_url}/api/v1/ingest",
            json=payload,
            headers=self._headers(),
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        return EventIngestResult(event_id=body["event_id"], status=body["status"], queued=bool(body["queued"]))

    def alerts(self, *, state: str | None = None, cursor: str | None = None, limit: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if state is not None:
            params["state"] = state
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit
        response = requests.get(
            f"{self._base_url}/api/v1/alerts",
            headers=self._headers(),
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    def metrics(self, window: str = "24h") -> dict[str, Any]:
        response = requests.get(
            f"{self._base_url}/api/v1/metrics",
            headers=self._headers(),
            params={"window": window},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    def config(self) -> PlatformConfig:
        response = requests.get(
            f"{self._base_url}/api/v1/config",
            headers=self._headers(),
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        return PlatformConfig(
            tenant_id=body["tenant_id"],
            anomaly_threshold=body.get("anomaly_threshold"),
            enabled_connectors=list(body.get("enabled_connectors") or []),
            model_version=body.get("model_version"),
            rule_overrides_json=dict(body.get("rule_overrides_json") or {}),
            connector_modules_loaded=list(body.get("connector_modules_loaded") or []),
        )
