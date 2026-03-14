from __future__ import annotations

import hashlib
import json
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _json(value: dict | list | None) -> str:
    return json.dumps(value or {}, default=str)


class ConnectorRepository:
    @staticmethod
    async def close_stale_runs(session: AsyncSession, *, stale_after_seconds: int) -> int:
        rows = await session.execute(
            text(
                """
                UPDATE connector_runs
                SET status = 'failed',
                    finished_at = NOW(),
                    details = COALESCE(details, '{}'::jsonb) || '{"error":"stale_run_recovered"}'::jsonb
                WHERE status = 'running'
                  AND started_at < NOW() - make_interval(secs => :stale_after_seconds)
                RETURNING run_id
                """
            ),
            {"stale_after_seconds": max(60, int(stale_after_seconds))},
        )
        closed = len(list(rows))
        await session.commit()
        return closed

    @staticmethod
    async def ensure_source_state(session: AsyncSession, source_name: str) -> None:
        await session.execute(
            text(
                """
                INSERT INTO source_connector_state (source_name, enabled, next_run_at)
                SELECT source_name, enabled, NOW()
                FROM event_sources
                WHERE source_name = :source_name
                ON CONFLICT (source_name) DO NOTHING
                """
            ),
            {"source_name": source_name},
        )

    @staticmethod
    async def source_runtime(session: AsyncSession, source_name: str) -> dict | None:
        await ConnectorRepository.ensure_source_state(session, source_name)
        row = await session.execute(
            text(
                """
                SELECT
                    es.source_name,
                    es.enabled AS source_enabled,
                    es.cadence_seconds,
                    es.freshness_slo_seconds,
                    COALESCE(scs.enabled, es.enabled) AS state_enabled,
                    scs.cursor_state,
                    scs.etag,
                    scs.last_modified,
                    scs.last_success_at,
                    scs.last_failure_at,
                    scs.consecutive_failures,
                    scs.backoff_until,
                    scs.next_run_at,
                    scs.degraded_reason
                FROM event_sources es
                LEFT JOIN source_connector_state scs ON scs.source_name = es.source_name
                WHERE es.source_name = :source_name
                LIMIT 1
                """
            ),
            {"source_name": source_name},
        )
        item = row.first()
        if not item:
            return None
        return dict(item._mapping)

    @staticmethod
    async def latest_watchlist_checksum(session: AsyncSession, source_name: str) -> str | None:
        row = await session.execute(
            text(
                """
                SELECT content_hash
                FROM watchlist_versions
                WHERE source_name = :source_name
                ORDER BY fetched_at DESC
                LIMIT 1
                """
            ),
            {"source_name": source_name},
        )
        return row.scalar_one_or_none()

    @staticmethod
    async def start_run(
        session: AsyncSession,
        *,
        source_name: str,
        cursor_state: dict | None = None,
    ) -> UUID:
        await ConnectorRepository.ensure_source_state(session, source_name)
        row = await session.execute(
            text(
                """
                INSERT INTO connector_runs (source_name, status, started_at, cursor_state)
                VALUES (:source_name, 'running', NOW(), CAST(:cursor_state AS jsonb))
                RETURNING run_id
                """
            ),
            {"source_name": source_name, "cursor_state": _json(cursor_state)},
        )
        run_id = row.scalar_one()
        await session.commit()
        return run_id

    @staticmethod
    async def finish_run(
        session: AsyncSession,
        *,
        run_id: UUID,
        source_name: str,
        status: str,
        fetched_records: int,
        upserted_records: int,
        checksum: str,
        cursor_state: dict | None,
        details: dict,
        error_code: str | None,
        next_run_seconds: int,
        backoff_seconds: int,
        degraded_reason: str | None = None,
    ) -> None:
        await session.execute(
            text(
                """
                UPDATE connector_runs
                SET status = :status,
                    finished_at = NOW(),
                    fetched_records = :fetched_records,
                    upserted_records = :upserted_records,
                    checksum = :checksum,
                    cursor_state = CAST(:cursor_state AS jsonb),
                    details = CAST(:details AS jsonb)
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": str(run_id),
                "status": status,
                "fetched_records": fetched_records,
                "upserted_records": upserted_records,
                "checksum": checksum,
                "cursor_state": _json(cursor_state),
                "details": _json(details),
            },
        )

        if status in {"success", "partial", "noop"}:
            await session.execute(
                text(
                    """
                    UPDATE source_connector_state
                    SET cursor_state = CAST(:cursor_state AS jsonb),
                        consecutive_failures = 0,
                        last_success_at = NOW(),
                        backoff_until = NULL,
                        degraded_reason = NULL,
                        next_run_at = NOW() + make_interval(secs => :next_run_seconds),
                        updated_at = NOW()
                    WHERE source_name = :source_name
                    """
                ),
                {
                    "source_name": source_name,
                    "cursor_state": _json(cursor_state),
                    "next_run_seconds": max(30, int(next_run_seconds)),
                },
            )
        else:
            await session.execute(
                text(
                    """
                    UPDATE source_connector_state
                    SET consecutive_failures = COALESCE(consecutive_failures, 0) + 1,
                        last_failure_at = NOW(),
                        backoff_until = NOW() + make_interval(secs => :backoff_seconds),
                        degraded_reason = :degraded_reason,
                        next_run_at = NOW() + make_interval(secs => :backoff_seconds),
                        updated_at = NOW()
                    WHERE source_name = :source_name
                    """
                ),
                {
                    "source_name": source_name,
                    "backoff_seconds": max(30, int(backoff_seconds)),
                    "degraded_reason": degraded_reason or error_code or "connector_error",
                },
            )
        await session.commit()

    @staticmethod
    async def record_error(
        session: AsyncSession,
        *,
        run_id: UUID | None,
        source_name: str,
        error_code: str,
        message: str,
        payload: dict,
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO connector_errors (run_id, source_name, error_code, message, payload)
                VALUES (:run_id, :source_name, :error_code, :message, CAST(:payload AS jsonb))
                """
            ),
            {
                "run_id": str(run_id) if run_id else None,
                "source_name": source_name,
                "error_code": error_code,
                "message": message,
                "payload": _json(payload),
            },
        )
        await session.commit()

    @staticmethod
    async def upsert_watchlist_version(
        session: AsyncSession,
        *,
        source_name: str,
        version: str,
        checksum: str,
        details: dict,
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO watchlist_versions (source_name, version, content_hash, fetched_at, metadata)
                VALUES (:source_name, :version, :checksum, NOW(), CAST(:details AS jsonb))
                ON CONFLICT (source_name, version)
                DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    fetched_at = NOW(),
                    metadata = EXCLUDED.metadata,
                    is_active = TRUE
                """
            ),
            {
                "source_name": source_name,
                "version": version,
                "checksum": checksum,
                "details": _json(details),
            },
        )

    @staticmethod
    async def upsert_sanctions_entities(session: AsyncSession, source_name: str, names: list[str]) -> int:
        upserts = 0
        for idx, name in enumerate(names):
            stable_hash = hashlib.sha1(name.encode("utf-8")).hexdigest()[:20]  # nosec B324 — non-crypto stable ID, not security-sensitive
            entity_id = f"{source_name}:{idx}:{stable_hash}"
            await session.execute(
                text(
                    """
                    INSERT INTO sanctions_entities (source_name, entity_id, primary_name, aliases, countries, metadata)
                    VALUES (:source_name, :entity_id, :primary_name, ARRAY[]::text[], ARRAY[]::text[], '{}'::jsonb)
                    ON CONFLICT (source_name, entity_id)
                    DO UPDATE SET
                        primary_name = EXCLUDED.primary_name,
                        last_seen = NOW(),
                        active = TRUE
                    """
                ),
                {
                    "source_name": source_name,
                    "entity_id": entity_id,
                    "primary_name": name,
                },
            )
            upserts += 1
        return upserts

    @staticmethod
    async def upsert_pep_entities(session: AsyncSession, source_name: str, names: list[str]) -> int:
        upserts = 0
        for idx, name in enumerate(names):
            stable_hash = hashlib.sha1(name.encode("utf-8")).hexdigest()[:20]  # nosec B324 — non-crypto stable ID, not security-sensitive
            entity_id = f"{source_name}:{idx}:{stable_hash}"
            await session.execute(
                text(
                    """
                    INSERT INTO pep_entities (source_name, entity_id, full_name, aliases, jurisdictions, metadata)
                    VALUES (:source_name, :entity_id, :full_name, ARRAY[]::text[], ARRAY[]::text[], '{}'::jsonb)
                    ON CONFLICT (source_name, entity_id)
                    DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        last_seen = NOW(),
                        active = TRUE
                    """
                ),
                {
                    "source_name": source_name,
                    "entity_id": entity_id,
                    "full_name": name,
                },
            )
            upserts += 1
        return upserts

    @staticmethod
    async def upsert_jurisdiction_risk(
        session: AsyncSession,
        source_name: str,
        jurisdiction_scores: dict[str, float],
    ) -> int:
        upserts = 0
        for code, score in jurisdiction_scores.items():
            risk_level = "high" if score >= 0.75 else "medium"
            await session.execute(
                text(
                    """
                    INSERT INTO jurisdiction_risk_scores (
                        source_name,
                        jurisdiction_code,
                        risk_score,
                        risk_level,
                        details,
                        updated_at
                    ) VALUES (
                        :source_name,
                        :jurisdiction_code,
                        :risk_score,
                        :risk_level,
                        '{}'::jsonb,
                        NOW()
                    )
                    ON CONFLICT (source_name, jurisdiction_code)
                    DO UPDATE SET
                        risk_score = EXCLUDED.risk_score,
                        risk_level = EXCLUDED.risk_level,
                        updated_at = NOW()
                    """
                ),
                {
                    "source_name": source_name,
                    "jurisdiction_code": code.upper(),
                    "risk_score": score,
                    "risk_level": risk_level,
                },
            )
            upserts += 1
        return upserts

    @staticmethod
    async def upsert_fx_rates(session: AsyncSession, source_name: str, rates: dict[str, float], rate_date: date | None = None) -> int:
        upserts = 0
        effective_date = rate_date or date.today()
        for pair, value in rates.items():
            if "_" not in pair:
                continue
            base, quote = pair.split("_", 1)
            await session.execute(
                text(
                    """
                    INSERT INTO fx_rates (source_name, base_currency, quote_currency, rate_date, rate, fetched_at)
                    VALUES (:source_name, :base_currency, :quote_currency, :rate_date, :rate, NOW())
                    ON CONFLICT (source_name, base_currency, quote_currency, rate_date)
                    DO UPDATE SET
                        rate = EXCLUDED.rate,
                        fetched_at = NOW()
                    """
                ),
                {
                    "source_name": source_name,
                    "base_currency": base.upper(),
                    "quote_currency": quote.upper(),
                    "rate_date": effective_date,
                    "rate": value,
                },
            )
            upserts += 1
        return upserts

    @staticmethod
    async def upsert_ip_intelligence(
        session: AsyncSession,
        *,
        source_name: str,
        ip: str,
        country_code: str | None,
        asn: str | None,
        is_proxy: bool | None,
        risk_score: float | None,
        raw: dict,
        ttl_seconds: int,
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO ip_intelligence_cache (ip, source_name, country_code, asn, is_proxy, risk_score, raw, fetched_at, expires_at)
                VALUES (
                    CAST(:ip AS inet),
                    :source_name,
                    :country_code,
                    :asn,
                    :is_proxy,
                    :risk_score,
                    CAST(:raw AS jsonb),
                    NOW(),
                    NOW() + make_interval(secs => :ttl_seconds)
                )
                ON CONFLICT (ip)
                DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    country_code = EXCLUDED.country_code,
                    asn = EXCLUDED.asn,
                    is_proxy = EXCLUDED.is_proxy,
                    risk_score = EXCLUDED.risk_score,
                    raw = EXCLUDED.raw,
                    fetched_at = NOW(),
                    expires_at = EXCLUDED.expires_at
                """
            ),
            {
                "ip": ip,
                "source_name": source_name,
                "country_code": country_code,
                "asn": asn,
                "is_proxy": is_proxy,
                "risk_score": risk_score,
                "raw": _json(raw),
                "ttl_seconds": max(60, int(ttl_seconds)),
            },
        )

    @staticmethod
    async def upsert_bin_intelligence(
        session: AsyncSession,
        *,
        source_name: str,
        bin_value: str,
        country_code: str | None,
        issuer: str | None,
        card_type: str | None,
        card_brand: str | None,
        prepaid: bool | None,
        raw: dict,
        ttl_seconds: int,
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO bin_intelligence_cache (
                    bin,
                    source_name,
                    country_code,
                    issuer,
                    card_type,
                    card_brand,
                    prepaid,
                    raw,
                    fetched_at,
                    expires_at
                ) VALUES (
                    :bin,
                    :source_name,
                    :country_code,
                    :issuer,
                    :card_type,
                    :card_brand,
                    :prepaid,
                    CAST(:raw AS jsonb),
                    NOW(),
                    NOW() + make_interval(secs => :ttl_seconds)
                )
                ON CONFLICT (bin)
                DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    country_code = EXCLUDED.country_code,
                    issuer = EXCLUDED.issuer,
                    card_type = EXCLUDED.card_type,
                    card_brand = EXCLUDED.card_brand,
                    prepaid = EXCLUDED.prepaid,
                    raw = EXCLUDED.raw,
                    fetched_at = NOW(),
                    expires_at = EXCLUDED.expires_at
                """
            ),
            {
                "bin": bin_value,
                "source_name": source_name,
                "country_code": country_code,
                "issuer": issuer,
                "card_type": card_type,
                "card_brand": card_brand,
                "prepaid": prepaid,
                "raw": _json(raw),
                "ttl_seconds": max(3600, int(ttl_seconds)),
            },
        )

    @staticmethod
    async def list_status(session: AsyncSession) -> list[dict]:
        rows = await session.execute(
            text(
                """
                WITH latest_runs AS (
                    SELECT DISTINCT ON (source_name)
                        source_name,
                        status,
                        started_at,
                        details
                    FROM connector_runs
                    ORDER BY source_name, started_at DESC
                )
                SELECT
                    es.source_name,
                    COALESCE(scs.enabled, es.enabled) AS enabled,
                    es.cadence_seconds,
                    es.freshness_slo_seconds,
                    lr.status AS latest_status,
                    lr.started_at AS latest_run_at,
                    scs.last_success_at,
                    scs.last_failure_at,
                    CASE
                        WHEN scs.last_success_at IS NULL THEN NULL
                        ELSE EXTRACT(EPOCH FROM (NOW() - scs.last_success_at))::INT
                    END AS freshness_seconds,
                    COALESCE(scs.consecutive_failures, 0) AS consecutive_failures,
                    scs.next_run_at,
                    scs.degraded_reason
                FROM event_sources es
                LEFT JOIN source_connector_state scs ON scs.source_name = es.source_name
                LEFT JOIN latest_runs lr ON lr.source_name = es.source_name
                ORDER BY es.source_name ASC
                """
            )
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def list_runs(session: AsyncSession, *, source_name: str | None, limit: int) -> list[dict]:
        where = ""
        params: dict = {"limit": limit}
        if source_name:
            where = "WHERE source_name = :source_name"
            params["source_name"] = source_name

        rows = await session.execute(
            text(
                f"""
                SELECT
                    run_id,
                    source_name,
                    status,
                    started_at,
                    finished_at,
                    fetched_records,
                    upserted_records,
                    checksum,
                    cursor_state,
                    details,
                    CASE
                        WHEN status IN ('failed', 'degraded') THEN details
                        ELSE '{{}}'::jsonb
                    END AS error_summary
                FROM connector_runs
                {where}
                ORDER BY started_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def list_errors(session: AsyncSession, *, source_name: str | None, limit: int) -> list[dict]:
        where = ""
        params: dict = {"limit": limit}
        if source_name:
            where = "WHERE source_name = :source_name"
            params["source_name"] = source_name
        rows = await session.execute(
            text(
                f"""
                SELECT id, run_id, source_name, error_code, message, payload, occurred_at
                FROM connector_errors
                {where}
                ORDER BY occurred_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def set_source_enabled(session: AsyncSession, *, source_name: str, enabled: bool) -> bool:
        await ConnectorRepository.ensure_source_state(session, source_name)
        event_source = await session.execute(
            text("SELECT 1 FROM event_sources WHERE source_name = :source_name LIMIT 1"),
            {"source_name": source_name},
        )
        if event_source.first() is None:
            await session.rollback()
            return False

        await session.execute(
            text(
                """
                UPDATE event_sources
                SET enabled = :enabled, updated_at = NOW()
                WHERE source_name = :source_name
                """
            ),
            {"source_name": source_name, "enabled": enabled},
        )
        await session.execute(
            text(
                """
                UPDATE source_connector_state
                SET enabled = :enabled,
                    next_run_at = CASE WHEN :enabled THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE source_name = :source_name
                """
            ),
            {"source_name": source_name, "enabled": enabled},
        )
        await session.commit()
        return True
