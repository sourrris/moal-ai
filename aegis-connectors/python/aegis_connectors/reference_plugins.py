from __future__ import annotations

import asyncio
import csv
import hashlib
import io
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import httpx
from app.application.connectors import BaseConnector, ConnectorResult, register_reference_connector
from app.config import get_settings
from risk_common.schemas_v2 import RiskEventIngestRequest, TransactionPayload

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


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _version_now() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")


_FATF_COUNTRY_CODES = {
    "algeria": "DZ",
    "angola": "AO",
    "bolivia": "BO",
    "bulgaria": "BG",
    "cameroon": "CM",
    "cote d'ivoire": "CI",
    "côte d'ivoire": "CI",
    "democratic people's republic of korea": "KP",
    "democratic republic of congo": "CD",
    "haiti": "HT",
    "iran": "IR",
    "kenya": "KE",
    "kuwait": "KW",
    "lao people's democratic republic": "LA",
    "lebanon": "LB",
    "monaco": "MC",
    "myanmar": "MM",
    "namibia": "NA",
    "nepal": "NP",
    "papua new guinea": "PG",
    "south sudan": "SS",
    "syria": "SY",
    "venezuela": "VE",
    "vietnam": "VN",
    "virgin islands (uk)": "VG",
    "yemen": "YE",
}

_FATF_BLACKLIST_20260213 = [
    "Democratic People's Republic of Korea",
    "Iran",
    "Myanmar",
]

_FATF_GREYLIST_20260213 = [
    "Algeria",
    "Angola",
    "Bolivia",
    "Bulgaria",
    "Cameroon",
    "Côte d'Ivoire",
    "Democratic Republic of Congo",
    "Haiti",
    "Kenya",
    "Kuwait",
    "Lao People's Democratic Republic",
    "Lebanon",
    "Monaco",
    "Namibia",
    "Nepal",
    "Papua New Guinea",
    "South Sudan",
    "Syria",
    "Venezuela",
    "Vietnam",
    "Virgin Islands (UK)",
    "Yemen",
]


def _fatf_country_codes(names: list[str]) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for name in names:
        code = _FATF_COUNTRY_CODES.get(name.strip().lower())
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _fatf_result(*, body: str, version: str, details: dict, high_risk: list[str], increased_monitoring: list[str]) -> ConnectorResult:
    jurisdiction_scores: dict[str, float] = {}
    for code in _fatf_country_codes(high_risk):
        jurisdiction_scores[code] = 0.95
    for code in _fatf_country_codes(increased_monitoring):
        jurisdiction_scores.setdefault(code, 0.8)

    fetched_records = len(high_risk) + len(increased_monitoring)
    return ConnectorResult(
        source_name="fatf",
        status="success",
        fetched_records=fetched_records,
        upserted_records=len(jurisdiction_scores),
        checksum=_checksum(body),
        version=version,
        details=details,
        jurisdiction_scores=jurisdiction_scores,
    )


@register_reference_connector
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

        version = response.headers.get("etag") or response.headers.get("last-modified") or _version_now()
        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(names),
            upserted_records=len(names),
            checksum=_checksum(body),
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


@register_reference_connector
class FatfConnector(BaseConnector):
    source_name = "fatf"
    config_enabled = settings.connector_enable_fatf

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (compatible; AegisRiskConnector/2.1; +https://localhost)",
        }
        try:
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
            lower_body = body.lower()
            high_risk = [name for name in _FATF_BLACKLIST_20260213 if name.lower() in lower_body]
            increased_monitoring = [name for name in _FATF_GREYLIST_20260213 if name.lower() in lower_body]

            if high_risk or increased_monitoring:
                return _fatf_result(
                    body=body,
                    version=datetime.now(tz=UTC).strftime("%Y%m%d"),
                    details={"source": "fatf-html"},
                    high_risk=high_risk,
                    increased_monitoring=increased_monitoring,
                )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise

        fallback_body = "\n".join(["2026-02-13"] + _FATF_BLACKLIST_20260213 + _FATF_GREYLIST_20260213)
        return _fatf_result(
            body=fallback_body,
            version="20260213",
            details={
                "source": "fatf-fallback",
                "fallback_reason": "fatf_site_blocked",
                "fallback_as_of": "2026-02-13",
                "fallback_blacklist_count": len(_FATF_BLACKLIST_20260213),
                "fallback_greylist_count": len(_FATF_GREYLIST_20260213),
            },
            high_risk=_FATF_BLACKLIST_20260213,
            increased_monitoring=_FATF_GREYLIST_20260213,
        )


@register_reference_connector
class EcbFxConnector(BaseConnector):
    source_name = "ecb_fx"
    config_enabled = settings.connector_enable_ecb

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
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
            checksum=_checksum(body),
            version=datetime.now(tz=UTC).strftime("%Y%m%d"),
            details={"source": "ecb-exr"},
            fx_rates=fx_rates,
            fx_rate_date=rate_date,
        )


@register_reference_connector
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
            event = RiskEventIngestRequest(
                idempotency_key=f"btc-{txid}",
                source="mempool_bitcoin",
                event_type="crypto_transaction",
                transaction=TransactionPayload(
                    transaction_id=txid,
                    amount=float(value) / 100_000_000.0,
                    currency="BTC",
                    metadata={
                        "vsize": vsize,
                        "fee": tx.get("fee"),
                    },
                ),
                occurred_at=datetime.now(tz=UTC),
            )
            events.append(event)

        body = response.text
        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(transactions),
            upserted_records=len(events),
            checksum=_checksum(body),
            version=_version_now(),
            details={"mode": "realtime-mempool"},
            events=events,
        )


@register_reference_connector
class AbuseChIPConnector(BaseConnector):
    source_name = "abusech_ip"
    config_enabled = settings.connector_enable_abusech

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        url = settings.abusech_ip_blocklist_url
        headers = {
            "Accept": "text/plain,text/csv;q=0.9,*/*;q=0.8",
            "User-Agent": "AegisRiskConnector/2.1 (threat-intel@aegis.local)",
        }
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "GET", url, headers=headers, follow_redirects=True)
            response.raise_for_status()

        body = response.text
        ip_records: list[dict] = []
        content_type = response.headers.get("content-type", "").lower()
        lines = [line.strip() for line in body.splitlines() if line.strip() and not line.lstrip().startswith("#")]

        if "csv" in content_type or any(line.count(",") >= 4 for line in lines):
            reader = csv.DictReader(
                io.StringIO("\n".join(lines)),
                fieldnames=["first_seen_utc", "dst_ip", "dst_port", "c2_status", "last_online", "threat"],
            )
            for row in reader:
                ip = str(row.get("dst_ip") or "").strip()
                if not ip:
                    continue
                status = str(row.get("c2_status") or "listed").strip().lower()
                threat = str(row.get("threat") or "botnet_c2").strip().lower()
                ip_records.append(
                    {
                        "ip": ip,
                        "risk_score": 0.95 if status == "online" else 0.8,
                        "raw": {
                            "status": status,
                            "threat": threat,
                            "source_feed": url,
                        },
                    }
                )
        else:
            seen: set[str] = set()
            for line in lines:
                ip = line.split()[0].strip()
                if not ip or ip in seen:
                    continue
                seen.add(ip)
                ip_records.append(
                    {
                        "ip": ip,
                        "risk_score": 0.95,
                        "raw": {
                            "status": "listed",
                            "threat": "botnet_c2",
                            "source_feed": url,
                        },
                    }
                )

        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(ip_records),
            upserted_records=len(ip_records),
            checksum=_checksum(body),
            version=_version_now(),
            details={
                "mode": "blocklist-download",
                "content_type": content_type,
                "source_feed": url,
            },
            ip_records=ip_records,
        )
