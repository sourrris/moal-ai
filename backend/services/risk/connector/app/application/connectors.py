from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from risk_common.schemas_v2 import RiskEventIngestRequest, TransactionPayload

from app.config import get_settings

settings = get_settings()


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(max(1, settings.connector_max_retries)):
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code >= 500 and attempt < settings.connector_max_retries - 1:
                await asyncio.sleep(min(2**attempt, 5))
                continue
            return response
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt >= settings.connector_max_retries - 1:
                break
            await asyncio.sleep(min(2**attempt, 5))
    assert last_exc is not None
    raise last_exc


@dataclass
class ConnectorResult:
    source_name: str
    status: str
    fetched_records: int
    upserted_records: int
    checksum: str
    version: str
    details: dict = field(default_factory=dict)
    cursor_state: dict = field(default_factory=dict)
    sanctions_names: list[str] = field(default_factory=list)
    pep_names: list[str] = field(default_factory=list)
    jurisdiction_scores: dict[str, float] = field(default_factory=dict)
    fx_rates: dict[str, float] = field(default_factory=dict)
    fx_rate_date: date | None = None
    ip_records: list[dict] = field(default_factory=list)
    bin_records: list[dict] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)


class BaseConnector:
    source_name: str
    config_enabled: bool = True

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def _checksum(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _now_version() -> str:
        return datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")

    @staticmethod
    def _disabled_result(source_name: str, reason: str) -> ConnectorResult:
        now = datetime.now(tz=UTC).isoformat()
        return ConnectorResult(
            source_name=source_name,
            status="degraded",
            fetched_records=0,
            upserted_records=0,
            checksum=hashlib.sha256(reason.encode("utf-8")).hexdigest(),
            version=now,
            details={"reason": reason},
        )


class OfacConnector(BaseConnector):
    source_name = "ofac_sls"
    config_enabled = settings.connector_enable_ofac

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        headers = {
            "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
            "User-Agent": "AegisRiskConnector/2.1 (compliance@aegis.local)",
        }
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(
                client,
                "GET",
                settings.ofac_sls_url,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()

        body = response.text
        reader = csv.reader(io.StringIO(body))
        names: list[str] = []
        seen: set[str] = set()
        for row in reader:
            if not row:
                continue
            candidate = row[1] if len(row) > 1 else row[0]
            normalized = str(candidate).strip().strip('"')
            if normalized.lower() in {"name", "sdn_name", "sdn name", "entity name"}:
                continue
            if normalized:
                clipped = normalized[:200]
                if clipped not in seen:
                    seen.add(clipped)
                    names.append(clipped)

        checksum = self._checksum(body)
        version = response.headers.get("etag") or response.headers.get("last-modified") or self._now_version()
        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(names),
            upserted_records=len(names),
            checksum=checksum,
            version=version[:120],
            details={
                "content_type": response.headers.get("content-type", ""),
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
            },
            sanctions_names=names,
            cursor_state={
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
            },
        )


class FatfConnector(BaseConnector):
    source_name = "fatf"
    config_enabled = settings.connector_enable_fatf

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (compatible; AegisRiskConnector/2.1; +https://localhost)",
        }
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(
                client,
                "GET",
                settings.fatf_source_url,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()

        body = response.text
        checksum = self._checksum(body)
        codes = sorted({code.upper() for code in re.findall(r"\b[A-Z]{2,3}\b", body) if len(code) in {2, 3}})
        jurisdiction_scores = {code: 0.8 for code in codes[:120]}
        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(codes),
            upserted_records=len(jurisdiction_scores),
            checksum=checksum,
            version=datetime.now(tz=UTC).strftime("%Y%m%d"),
            details={"source": "fatf-html"},
            jurisdiction_scores=jurisdiction_scores,
        )


class EcbFxConnector(BaseConnector):
    source_name = "ecb_fx"
    config_enabled = settings.connector_enable_ecb

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        # Endpoint pattern returns 1 EUR quoted in each currency, including USD.
        url = f"{settings.ecb_fx_url.rstrip('/')}/EXR/D..EUR.SP00.A"
        params = {"lastNObservations": 1, "format": "csvdata"}
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "GET", url, params=params)
            response.raise_for_status()

        body = response.text
        reader = csv.DictReader(io.StringIO(body))
        quote_per_eur: dict[str, float] = {}
        rate_date: date | None = None
        for row in reader:
            quote_currency = (
                row.get("CURRENCY")
                or row.get("QUOTE_CURRENCY")
                or row.get("CURRENCY_DENOM")
                or row.get("currency")
                or ""
            )
            raw_rate = row.get("OBS_VALUE") or row.get("obs_value")
            raw_date = row.get("TIME_PERIOD") or row.get("time_period")
            if raw_date and not rate_date:
                try:
                    rate_date = date.fromisoformat(raw_date[:10])
                except ValueError:
                    rate_date = None
            if not quote_currency or raw_rate is None:
                continue
            try:
                parsed = float(Decimal(str(raw_rate)))
            except (InvalidOperation, ValueError):
                continue
            if parsed > 0:
                quote_per_eur[str(quote_currency).upper()] = parsed

        usd_per_eur = quote_per_eur.get("USD")
        fx_rates: dict[str, float] = {"USD_USD": 1.0}
        if usd_per_eur:
            fx_rates["EUR_USD"] = float(usd_per_eur)
            for currency, quote_rate in quote_per_eur.items():
                if currency == "USD":
                    continue
                fx_rates[f"{currency}_USD"] = float(usd_per_eur / quote_rate)

        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(quote_per_eur),
            upserted_records=len(fx_rates),
            checksum=self._checksum(body),
            version=datetime.now(tz=UTC).strftime("%Y%m%d"),
            details={"source": "ecb-exr"},
            fx_rates=fx_rates,
            fx_rate_date=rate_date,
        )


class MempoolBitcoinConnector(BaseConnector):
    source_name = "mempool_bitcoin"
    config_enabled = settings.connector_enable_mempool

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        url = f"{settings.mempool_api_url.rstrip('/')}/mempool/recent"
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "GET", url)
            response.raise_for_status()

        transactions = response.json()
        events: list[RiskEventIngestRequest] = []
        for tx in transactions:
            txid = tx.get("txid")
            value = tx.get("value", 0)
            vsize = tx.get("vsize", 0)
            
            # Map BTC tx to RiskEvent schema
            event = RiskEventIngestRequest(
                idempotency_key=f"btc-{txid}",
                source="mempool_bitcoin",
                event_type="crypto_transaction",
                transaction=TransactionPayload(
                    transaction_id=txid,
                    amount=float(value) / 100_000_000.0, # satoshis to BTC
                    currency="BTC",
                    metadata={
                        "vsize": vsize,
                        "fee": tx.get("fee"),
                    }
                ),
                occurred_at=datetime.now(tz=UTC)
            )
            events.append(event)

        body = response.text
        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(transactions),
            upserted_records=len(events),
            checksum=self._checksum(body),
            version=self._now_version(),
            details={"mode": "realtime-mempool"},
            events=events
        )


class AbuseChIPConnector(BaseConnector):
    source_name = "abusech_ip"
    config_enabled = settings.connector_enable_abusech

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        # Fetching the IP blocklist (CSV format)
        url = "https://abuse.ch/downloads/ipblocklist.csv"
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "GET", url)
            response.raise_for_status()

        body = response.text
        # Skip comment lines starting with #
        lines = [line for line in body.splitlines() if line and not line.startswith("#")]
        reader = csv.DictReader(io.StringIO("\n".join(lines)), fieldnames=["first_seen_utc", "dst_ip", "dst_port", "c2_status", "last_online", "threat"])
        
        ip_records: list[dict] = []
        for row in reader:
            ip_records.append({
                "ip": row["dst_ip"],
                "threat": row["threat"],
                "status": row["c2_status"],
                "risk_score": 0.95 if row["c2_status"] == "online" else 0.7
            })

        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(ip_records),
            upserted_records=len(ip_records),
            checksum=self._checksum(body),
            version=self._now_version(),
            details={"mode": "blocklist-download"},
            ip_records=ip_records
        )


def default_connectors() -> list[BaseConnector]:
    return [
        OfacConnector(),
        FatfConnector(),
        EcbFxConnector(),
        MempoolBitcoinConnector(),
        AbuseChIPConnector(),
    ]
