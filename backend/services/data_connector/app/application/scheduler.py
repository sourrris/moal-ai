from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx
from risk_common.messaging import publish_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.connectors import BaseConnector, ConnectorResult, default_connectors
from app.config import get_settings
from app.infrastructure.db import SessionLocal
from app.infrastructure.repository import ConnectorRepository

logger = logging.getLogger(__name__)
settings = get_settings()


def classify_connector_error(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "transient_network"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in {401, 403}:
            return "auth"
        if code == 404:
            return "source_not_found"
        if code == 429:
            return "rate_limit"
        if 500 <= code < 600:
            return "transient_network"
        return "parse_error"
    if isinstance(exc, httpx.RequestError):
        return "transient_network"
    if isinstance(exc, (ValueError, KeyError)):
        return "parse_error"
    return "connector_failure"


class ConnectorScheduler:
    def __init__(self, rabbit_channel, connectors: list[BaseConnector] | None = None):
        self.rabbit_channel = rabbit_channel
        resolved = connectors or default_connectors()
        self.connectors = resolved
        self.connector_map = {connector.source_name: connector for connector in resolved}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        stale_after = max(300, settings.connector_http_timeout_seconds * max(1, settings.connector_max_retries) * 2)
        async with SessionLocal() as session:
            closed = await ConnectorRepository.close_stale_runs(session, stale_after_seconds=stale_after)
        if closed:
            logger.warning("connector_stale_runs_recovered", extra={"closed_runs": closed})
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run_loop(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(max(10, settings.connector_poll_seconds))

    async def run_once(self, source_name: str | None = None) -> None:
        if not settings.connectors_v2_enabled:
            return
        connectors = [self.connector_map[source_name]] if source_name and source_name in self.connector_map else self.connectors
        for connector in connectors:
            try:
                if await self._should_run(connector.source_name):
                    await self._run_connector(connector)
            except Exception as exc:  # noqa: BLE001
                logger.exception("connector_scheduler_iteration_failed", extra={"source": connector.source_name, "error": str(exc)})

    async def _should_run(self, source_name: str) -> bool:
        async with SessionLocal() as session:
            runtime = await ConnectorRepository.source_runtime(session, source_name)
        if not runtime:
            return False
        if not bool(runtime.get("source_enabled", False)) or not bool(runtime.get("state_enabled", False)):
            return False

        now = datetime.now(tz=UTC)
        backoff_until = runtime.get("backoff_until")
        next_run_at = runtime.get("next_run_at")
        if backoff_until and now < backoff_until:
            return False
        if next_run_at and now < next_run_at:
            return False
        return True

    async def _run_connector(self, connector: BaseConnector) -> None:
        run_id = None
        runtime: dict | None = None
        async with SessionLocal() as session:
            runtime = await ConnectorRepository.source_runtime(session, connector.source_name)
            if not runtime:
                return
            run_id = await ConnectorRepository.start_run(
                session,
                source_name=connector.source_name,
                cursor_state=runtime.get("cursor_state") if isinstance(runtime.get("cursor_state"), dict) else {},
            )

        assert runtime is not None
        cadence_seconds = int(runtime.get("cadence_seconds") or settings.connector_poll_seconds)
        previous_failures = int(runtime.get("consecutive_failures") or 0)

        try:
            fetch_timeout = settings.connector_http_timeout_seconds * max(1, settings.connector_max_retries) + 10
            result = await asyncio.wait_for(connector.fetch(runtime_state=runtime), timeout=fetch_timeout)
            async with SessionLocal() as session:
                previous_checksum = await ConnectorRepository.latest_watchlist_checksum(session, connector.source_name)
                upserts = 0
                status = result.status
                details = dict(result.details or {})

                if status in {"success", "partial"} and previous_checksum and previous_checksum == result.checksum:
                    status = "noop"
                    details["unchanged_checksum"] = True
                elif status in {"success", "partial"}:
                    upserts = await self._persist_result(session, result)
                    await session.commit()

                await ConnectorRepository.finish_run(
                    session,
                    run_id=run_id,
                    source_name=connector.source_name,
                    status=status,
                    fetched_records=result.fetched_records,
                    upserted_records=upserts,
                    checksum=result.checksum,
                    cursor_state=result.cursor_state,
                    details=details,
                    error_code=None if status != "degraded" else "config_missing",
                    next_run_seconds=cadence_seconds,
                    backoff_seconds=max(300, cadence_seconds),
                    degraded_reason=details.get("reason") if status == "degraded" else None,
                )

                if status == "degraded":
                    await ConnectorRepository.record_error(
                        session,
                        run_id=run_id,
                        source_name=connector.source_name,
                        error_code="config_missing",
                        message=str(details.get("reason") or "connector degraded"),
                        payload=details,
                    )

            await publish_json(
                channel=self.rabbit_channel,
                exchange_name=settings.rabbitmq_reference_exchange,
                routing_key=settings.rabbitmq_reference_routing_key,
                payload={
                    "source_name": result.source_name,
                    "status": status,
                    "fetched_records": result.fetched_records,
                    "upserted_records": upserts,
                    "version": result.version,
                    "checksum": result.checksum,
                    "updated_at": datetime.now(tz=UTC).isoformat(),
                },
                headers={"x-schema-version": 2},
            )
        except Exception as exc:  # noqa: BLE001
            error_code = classify_connector_error(exc)
            logger.exception("connector_run_failed", extra={"source": connector.source_name, "error_code": error_code, "error": str(exc)})

            if error_code in {"auth", "source_not_found"}:
                backoff_seconds = max(3600, cadence_seconds)
                status = "degraded"
            else:
                retry_seconds = min(settings.connector_backoff_max_seconds, max(60, (2 ** min(previous_failures + 1, 6)) * 30))
                backoff_seconds = retry_seconds
                status = "failed"

            async with SessionLocal() as session:
                if run_id is not None:
                    await ConnectorRepository.finish_run(
                        session,
                        run_id=run_id,
                        source_name=connector.source_name,
                        status=status,
                        fetched_records=0,
                        upserted_records=0,
                        checksum="",
                        cursor_state={},
                        details={"error": str(exc), "error_code": error_code},
                        error_code=error_code,
                        next_run_seconds=cadence_seconds,
                        backoff_seconds=backoff_seconds,
                        degraded_reason=str(exc) if status == "degraded" else None,
                    )
                await ConnectorRepository.record_error(
                    session,
                    run_id=run_id,
                    source_name=connector.source_name,
                    error_code=error_code,
                    message=str(exc),
                    payload={"exception": type(exc).__name__},
                )

    async def _persist_result(self, session: AsyncSession, result: ConnectorResult) -> int:
        upserts = 0

        await ConnectorRepository.upsert_watchlist_version(
            session,
            source_name=result.source_name,
            version=result.version,
            checksum=result.checksum,
            details=result.details,
        )

        if result.sanctions_names:
            upserts += await ConnectorRepository.upsert_sanctions_entities(
                session,
                result.source_name,
                result.sanctions_names,
            )

        if result.pep_names:
            upserts += await ConnectorRepository.upsert_pep_entities(
                session,
                result.source_name,
                result.pep_names,
            )

        if result.jurisdiction_scores:
            upserts += await ConnectorRepository.upsert_jurisdiction_risk(
                session,
                result.source_name,
                result.jurisdiction_scores,
            )

        if result.fx_rates:
            upserts += await ConnectorRepository.upsert_fx_rates(
                session,
                result.source_name,
                result.fx_rates,
                rate_date=result.fx_rate_date,
            )

        if result.ip_records:
            for item in result.ip_records:
                await ConnectorRepository.upsert_ip_intelligence(
                    session,
                    source_name=result.source_name,
                    ip=str(item["ip"]),
                    country_code=item.get("country_code"),
                    asn=item.get("asn"),
                    is_proxy=item.get("is_proxy"),
                    risk_score=item.get("risk_score"),
                    raw=item.get("raw") or {},
                    ttl_seconds=86400,
                )
                upserts += 1

        if result.bin_records:
            for item in result.bin_records:
                await ConnectorRepository.upsert_bin_intelligence(
                    session,
                    source_name=result.source_name,
                    bin_value=str(item["bin"]),
                    country_code=item.get("country_code"),
                    issuer=item.get("issuer"),
                    card_type=item.get("card_type"),
                    card_brand=item.get("card_brand"),
                    prepaid=item.get("prepaid"),
                    raw=item.get("raw") or {},
                    ttl_seconds=2592000,
                )
                upserts += 1

        if upserts == 0:
            upserts = result.upserted_records
        return upserts
