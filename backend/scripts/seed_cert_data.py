#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"
DEFAULT_SOURCE = "cert_dataset"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed moal-ai with CERT logon.csv data.")
    parser.add_argument("--csv", dest="csv_path", type=Path, help="Path to CERT logon.csv")
    parser.add_argument("--csv-url", dest="csv_url", help="Optional URL to download CERT logon.csv from")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="API username")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="API password")
    parser.add_argument("--chunk-size", type=int, default=250, help="Batch size for ingest requests")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of rows to ingest")
    parser.add_argument(
        "--register-if-missing",
        action="store_true",
        help="Register the user when token issuance fails with bad credentials",
    )
    return parser.parse_args()


def normalize_row(row: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[key.strip().lower()] = str(value or "").strip()
    return normalized


def parse_timestamp(value: str) -> datetime:
    candidate = value.strip()
    for fmt in (
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(candidate, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue

    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def infer_failed_auth(row: dict[str, str]) -> bool:
    for key in ("result", "status", "outcome", "success", "failed", "is_success"):
        value = row.get(key, "").lower()
        if value in {"false", "0", "fail", "failed", "failure", "denied", "error"}:
            return True
        if value in {"true", "1", "success", "succeeded", "ok", "passed"}:
            return False
    activity = row.get("activity", "").lower()
    return "fail" in activity or "denied" in activity


def build_event(row: dict[str, str]) -> dict[str, Any]:
    activity = row.get("activity", "") or "Logon"
    failed = infer_failed_auth(row)
    occurred_at = parse_timestamp(row["date"])
    user_identifier = row.get("user") or row.get("username")
    device = row.get("pc") or row.get("device") or row.get("host")

    if not user_identifier:
        raise ValueError("Missing user field in CERT row")

    return {
        "user_identifier": user_identifier,
        "event_type": "auth",
        "source": DEFAULT_SOURCE,
        "device_fingerprint": device or None,
        "request_count": 1,
        "failed_auth_count": 1 if failed else 0,
        "status_code": 401 if failed else 200,
        "occurred_at": occurred_at.isoformat(),
        "metadata": {
            "activity": activity,
            "dataset": "CERT r6.2",
            "raw": row,
        },
    }


def resolve_csv_source(csv_path: Path | None, csv_url: str | None) -> Path:
    if csv_path:
        return csv_path.expanduser().resolve()
    if not csv_url:
        raise SystemExit("Provide --csv or --csv-url to load CERT logon.csv.")

    with urlopen(csv_url) as response:  # noqa: S310
        payload = response.read()

    temp_dir = Path(tempfile.mkdtemp(prefix="moal-cert-seed-"))
    output_path = temp_dir / "logon.csv"
    output_path.write_bytes(payload)
    return output_path


def load_events(path: Path, limit: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = normalize_row(row)
            if not normalized.get("date") or not normalized.get("user"):
                continue
            events.append(build_event(normalized))
            if limit > 0 and len(events) >= limit:
                break
    return events


def chunked(items: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


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


def upload_events(
    client: httpx.Client,
    base_url: str,
    token: str,
    events: list[dict[str, Any]],
    chunk_size: int,
) -> tuple[int, int, int]:
    accepted = 0
    duplicates = 0
    failed = 0

    for batch in chunked(events, chunk_size):
        response = client.post(
            f"{base_url}/api/events/ingest/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={"events": batch},
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        accepted += int(payload.get("accepted", 0))
        duplicates += int(payload.get("duplicates", 0))
        failed += int(payload.get("failed", 0))

    return accepted, duplicates, failed


def main() -> int:
    args = parse_args()
    csv_path = resolve_csv_source(args.csv_path, args.csv_url)
    events = load_events(csv_path, args.limit)

    if not events:
        print(f"No valid events found in {csv_path}", file=sys.stderr)
        return 1

    with httpx.Client() as client:
        token = issue_token(
            client,
            args.base_url.rstrip("/"),
            args.username,
            args.password,
            register_if_missing=args.register_if_missing,
        )
        accepted, duplicates, failed = upload_events(
            client,
            args.base_url.rstrip("/"),
            token,
            events,
            max(1, min(args.chunk_size, 500)),
        )

    print(
        f"Seeded CERT data from {csv_path} | rows={len(events)} accepted={accepted} duplicates={duplicates} failed={failed}"
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
