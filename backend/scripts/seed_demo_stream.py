#!/usr/bin/env python3

from __future__ import annotations

import argparse
import random
import time
from datetime import UTC, datetime
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"

AUTH_SOURCES = ["okta", "azure_ad", "vpn_gateway"]
API_SOURCES = ["nginx_access", "api_gateway"]
SESSION_SOURCES = ["workspace_agent", "vpn_gateway"]
COUNTRIES = ["US", "GB", "DE", "IN", "SG", "AU", "CA", "BR"]
ENDPOINTS = ["/api/events", "/api/models/active", "/api/overview/metrics", "/api/dashboard/stats", "/login"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream synthetic moal-ai demo events.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="API username")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="API password")
    parser.add_argument("--batch-size", type=int, default=20, help="Events to send per batch")
    parser.add_argument("--sleep-seconds", type=float, default=3.0, help="Delay between batches")
    parser.add_argument("--iterations", type=int, default=0, help="Number of batches to send. 0 = run forever")
    parser.add_argument(
        "--register-if-missing",
        action="store_true",
        help="Register the user when token issuance fails with bad credentials",
    )
    return parser.parse_args()


def issue_token(
    client: httpx.Client,
    base_url: str,
    username: str,
    password: str,
    *,
    register_if_missing: bool,
) -> str:
    payload = {"username": username, "password": password}
    response = client.post(f"{base_url}/api/auth/token", json=payload, timeout=15.0)
    if response.status_code == 200:
        return response.json()["access_token"]

    if register_if_missing and response.status_code in {401, 404}:
        register = client.post(f"{base_url}/api/auth/register", json=payload, timeout=15.0)
        register.raise_for_status()
        return register.json()["access_token"]

    response.raise_for_status()
    raise RuntimeError("Unable to acquire access token")


def load_socfaker() -> Any | None:
    try:
        from socfaker import SocFaker  # type: ignore
    except Exception:
        return None
    return SocFaker()


def _maybe_value(candidate: Any) -> str | None:
    if candidate is None:
        return None
    if callable(candidate):
        try:
            candidate = candidate()
        except TypeError:
            return None
    return candidate if isinstance(candidate, str) else None


def build_user_pool() -> list[dict[str, str]]:
    users: list[dict[str, str]] = []
    for index in range(1, 41):
        users.append(
            {
                "user_identifier": f"user{index:04d}",
                "home_country": random.choice(COUNTRIES[:5]),
            }
        )
    return users


def build_event(user: dict[str, str], socfaker: Any | None, device_cache: dict[str, str]) -> dict[str, Any]:
    event_type = random.choices(
        population=["auth", "api_call", "session"],
        weights=[0.6, 0.25, 0.15],
        k=1,
    )[0]
    is_suspicious = random.random() > 0.92

    computer = getattr(socfaker, "computer", None)
    device_name = device_cache.setdefault(
        user["user_identifier"],
        _maybe_value(getattr(computer, "name", None)) or f"workstation-{random.randint(100, 999)}",
    )
    if is_suspicious and random.random() > 0.5:
        device_name = f"unknown-{random.randint(1000, 9999)}"

    source_ip = (
        _maybe_value(getattr(computer, "ipv4", None))
        or f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    )
    user_agent_obj = getattr(socfaker, "user_agent", None)
    user_agent = _maybe_value(getattr(user_agent_obj, "get", None)) or _maybe_value(user_agent_obj)
    if user_agent is None:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    geo_country = random.choice(COUNTRIES) if is_suspicious else user["home_country"]
    occurred_at = datetime.now(tz=UTC).isoformat()

    base_event: dict[str, Any] = {
        "user_identifier": user["user_identifier"],
        "event_type": event_type,
        "source_ip": source_ip,
        "user_agent": user_agent,
        "geo_country": geo_country,
        "device_fingerprint": device_name,
        "occurred_at": occurred_at,
        "metadata": {
            "generator": "soc_faker_demo_stream" if socfaker is not None else "demo_stream",
            "suspicious": is_suspicious,
        },
    }

    if event_type == "auth":
        failed = is_suspicious or random.random() < 0.08
        base_event.update(
            {
                "source": random.choice(AUTH_SOURCES),
                "request_count": 1,
                "failed_auth_count": 1 if failed else 0,
                "status_code": 401 if failed else 200,
            }
        )
        return base_event

    if event_type == "api_call":
        status_code = random.choice([200, 200, 200, 201, 204, 429, 500 if is_suspicious else 200])
        request_count = random.randint(2, 18 if is_suspicious else 8)
        base_event.update(
            {
                "source": random.choice(API_SOURCES),
                "endpoint": random.choice(ENDPOINTS),
                "request_count": request_count,
                "bytes_transferred": random.randint(32_000, 3_000_000),
                "status_code": status_code,
            }
        )
        return base_event

    base_event.update(
        {
            "source": random.choice(SESSION_SOURCES),
            "session_duration_seconds": random.randint(60, 36_000 if is_suspicious else 14_400),
            "request_count": random.randint(1, 6),
            "status_code": 200,
        }
    )
    return base_event


def send_batch(client: httpx.Client, base_url: str, token: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    response = client.post(
        f"{base_url}/api/events/ingest/batch",
        headers={"Authorization": f"Bearer {token}"},
        json={"events": events},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    batch_size = max(1, min(args.batch_size, 500))
    users = build_user_pool()
    device_cache: dict[str, str] = {}
    socfaker = load_socfaker()

    with httpx.Client() as client:
        token = issue_token(
            client,
            base_url,
            args.username,
            args.password,
            register_if_missing=args.register_if_missing,
        )

        iteration = 0
        while args.iterations == 0 or iteration < args.iterations:
            events = [build_event(random.choice(users), socfaker, device_cache) for _ in range(batch_size)]
            payload = send_batch(client, base_url, token, events)
            iteration += 1
            print(
                f"batch={iteration} accepted={payload.get('accepted', 0)} "
                f"duplicates={payload.get('duplicates', 0)} failed={payload.get('failed', 0)}"
            )

            if args.iterations != 0 and iteration >= args.iterations:
                break
            time.sleep(max(args.sleep_seconds, 0.0))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
