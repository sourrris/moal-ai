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
            response = await request_with_retry(client, "GET", settings.ofac_sls_url, headers=headers)
            response.raise_for_status()

        body = response.text
        reader = csv.DictReader(io.StringIO(body))
        names: list[str] = []
        for row in reader:
            candidate = (
                row.get("name")
                or row.get("sdn_name")
                or row.get("Name")
                or row.get("SDN_Name")
                or row.get("Entity Name")
                or ""
            )
            normalized = str(candidate).strip()
            if normalized:
                names.append(normalized[:200])

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


class OpenSanctionsConnector(BaseConnector):
    source_name = "opensanctions"
    config_enabled = settings.connector_enable_opensanctions

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        if not settings.opensanctions_api_key:
            return self._disabled_result(self.source_name, "missing OPENSANCTIONS_API_KEY")

        payload = {"queries": ["john doe"], "limit": 50}
        headers = {"Authorization": f"ApiKey {settings.opensanctions_api_key}"}
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "POST", settings.opensanctions_url, json=payload, headers=headers)
            if response.status_code in {401, 403}:
                return self._disabled_result(self.source_name, "invalid OPENSANCTIONS_API_KEY")
            response.raise_for_status()

        data = response.json() if response.content else {}
        results = data.get("results") if isinstance(data, dict) else []
        pep_names: list[str] = []
        for item in results if isinstance(results, list) else []:
            if isinstance(item, dict):
                caption = item.get("caption") or item.get("name")
                if caption:
                    pep_names.append(str(caption)[:200])

        body = response.text
        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(results) if isinstance(results, list) else 0,
            upserted_records=len(pep_names),
            checksum=self._checksum(body),
            version=self._now_version(),
            details={"mode": "api-match"},
            pep_names=pep_names,
        )


class FatfConnector(BaseConnector):
    source_name = "fatf"
    config_enabled = settings.connector_enable_fatf

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "GET", settings.fatf_source_url)
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


class MaxMindConnector(BaseConnector):
    source_name = "maxmind_geolite2"
    config_enabled = settings.connector_enable_maxmind

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        if not settings.maxmind_download_url:
            return self._disabled_result(self.source_name, "missing MAXMIND_DOWNLOAD_URL")
        if not settings.maxmind_license_key:
            return self._disabled_result(self.source_name, "missing MAXMIND_LICENSE_KEY")

        headers = {"Authorization": f"Bearer {settings.maxmind_license_key}"}
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "GET", settings.maxmind_download_url, headers=headers)
            if response.status_code in {401, 403}:
                return self._disabled_result(self.source_name, "invalid MAXMIND_LICENSE_KEY")
            response.raise_for_status()

        # Seed format: ip,country_code,asn,is_proxy,risk_score
        body = response.text
        reader = csv.DictReader(io.StringIO(body))
        records: list[dict[str, Any]] = []
        for row in reader:
            ip_value = str(row.get("ip", "")).strip()
            if not ip_value:
                continue
            risk_raw = row.get("risk_score")
            risk_value: float | None = None
            if risk_raw not in {None, ""}:
                try:
                    risk_value = float(risk_raw)
                except ValueError:
                    risk_value = None
            is_proxy_value = str(row.get("is_proxy", "")).strip().lower() in {"1", "true", "yes"}
            records.append(
                {
                    "ip": ip_value,
                    "country_code": str(row.get("country_code", "") or "").upper() or None,
                    "asn": str(row.get("asn", "") or "").upper() or None,
                    "is_proxy": is_proxy_value,
                    "risk_score": risk_value,
                    "raw": row,
                }
            )

        return ConnectorResult(
            source_name=self.source_name,
            status="success",
            fetched_records=len(records),
            upserted_records=len(records),
            checksum=self._checksum(body),
            version=self._now_version(),
            details={"mode": "seed-download"},
            ip_records=records,
        )


class IpinfoConnector(BaseConnector):
    source_name = "ipinfo"
    config_enabled = settings.connector_enable_ipinfo

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        if not settings.ipinfo_token:
            return self._disabled_result(self.source_name, "missing IPINFO_TOKEN")
        return ConnectorResult(
            source_name=self.source_name,
            status="noop",
            fetched_records=0,
            upserted_records=0,
            checksum=self._checksum("ipinfo:on-demand"),
            version=self._now_version(),
            details={"mode": "on_demand_lookup"},
        )

    async def lookup_ip(self, ip: str) -> dict | None:
        if not settings.ipinfo_token:
            return None
        params = {"token": settings.ipinfo_token}
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "GET", f"{settings.ipinfo_base_url.rstrip('/')}/{ip}/json", params=params)
            if response.status_code in {401, 403, 404}:
                return None
            response.raise_for_status()
        data = response.json() if response.content else {}
        if not isinstance(data, dict):
            return None
        privacy = data.get("privacy") if isinstance(data.get("privacy"), dict) else {}
        asn = data.get("org")
        risk_score = 0.9 if privacy.get("proxy") else 0.35
        return {
            "ip": ip,
            "country_code": (data.get("country") or "").upper() or None,
            "asn": str(asn)[:32] if asn else None,
            "is_proxy": bool(privacy.get("proxy")) if privacy else False,
            "risk_score": risk_score,
            "raw": data,
        }


class BinlistConnector(BaseConnector):
    source_name = "binlist"
    config_enabled = settings.connector_enable_binlist

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        return ConnectorResult(
            source_name=self.source_name,
            status="noop",
            fetched_records=0,
            upserted_records=0,
            checksum=self._checksum("binlist:on-demand"),
            version=self._now_version(),
            details={"mode": "on_demand_lookup"},
        )

    async def lookup_bin(self, card_bin: str) -> dict | None:
        async with httpx.AsyncClient(timeout=settings.connector_http_timeout_seconds) as client:
            response = await request_with_retry(client, "GET", f"{settings.binlist_base_url.rstrip('/')}/{card_bin}")
            if response.status_code in {404, 429}:
                return None
            response.raise_for_status()
        data = response.json() if response.content else {}
        if not isinstance(data, dict):
            return None

        country = data.get("country") if isinstance(data.get("country"), dict) else {}
        bank = data.get("bank") if isinstance(data.get("bank"), dict) else {}
        return {
            "bin": card_bin,
            "country_code": (country.get("alpha2") or "").upper() or None,
            "issuer": bank.get("name"),
            "card_type": data.get("type"),
            "card_brand": data.get("scheme"),
            "prepaid": data.get("prepaid"),
            "raw": data,
        }


class HibpConnector(BaseConnector):
    source_name = "hibp"
    config_enabled = settings.connector_enable_hibp

    async def fetch(self, runtime_state: dict | None = None) -> ConnectorResult:
        if not settings.hibp_api_key:
            return self._disabled_result(self.source_name, "missing HIBP_API_KEY")
        return ConnectorResult(
            source_name=self.source_name,
            status="noop",
            fetched_records=0,
            upserted_records=0,
            checksum=self._checksum("hibp:on-demand"),
            version=self._now_version(),
            details={"mode": "on_demand_lookup"},
        )


def default_connectors() -> list[BaseConnector]:
    return [
        OfacConnector(),
        OpenSanctionsConnector(),
        FatfConnector(),
        EcbFxConnector(),
        MaxMindConnector(),
        IpinfoConnector(),
        BinlistConnector(),
        HibpConnector(),
    ]
