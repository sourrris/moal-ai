from datetime import datetime
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Event, User
from risk_common.schemas import EventEnvelope

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRepository:
    @staticmethod
    async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            return None

        # Allow plaintext seeds in local/dev while keeping bcrypt support for production.
        if user.password_hash.startswith("$2"):
            if not pwd_context.verify(password, user.password_hash):
                return None
        elif user.password_hash != password:
            return None
        return user


class EventRepository:
    @staticmethod
    async def create_if_absent(
        session: AsyncSession,
        event: EventEnvelope,
        submitted_by: str,
    ) -> bool:
        stmt = (
            pg_insert(Event)
            .values(
                event_id=event.event_id,
                tenant_id=event.tenant_id,
                source=event.source,
                event_type=event.event_type,
                payload=event.payload,
                features=event.features,
                status="queued",
                submitted_by=submitted_by,
                occurred_at=event.occurred_at,
                ingested_at=event.ingested_at,
            )
            .on_conflict_do_nothing(index_elements=[Event.event_id])
        )
        result = await session.execute(stmt)
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def mark_status(session: AsyncSession, event_id: UUID, status: str) -> None:
        await session.execute(update(Event).where(Event.event_id == event_id).values(status=status))
        await session.commit()

    @staticmethod
    async def fetch_by_id(session: AsyncSession, event_id: UUID) -> Event | None:
        result = await session.execute(select(Event).where(Event.event_id == event_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_events(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        status: str | None,
        source: str | None,
        event_type: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> dict:
        try:
            offset = int(cursor or 0)
        except ValueError:
            offset = 0
        where_clauses = ["1=1"]
        params: dict = {"offset": offset, "limit": limit}

        if tenant_id:
            where_clauses.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if status:
            where_clauses.append("status = :status")
            params["status"] = status
        if source:
            where_clauses.append("source = :source")
            params["source"] = source
        if event_type:
            where_clauses.append("event_type = :event_type")
            params["event_type"] = event_type
        if from_ts:
            where_clauses.append("ingested_at >= :from_ts")
            params["from_ts"] = from_ts
        if to_ts:
            where_clauses.append("ingested_at <= :to_ts")
            params["to_ts"] = to_ts

        where_sql = " AND ".join(where_clauses)

        rows = await session.execute(
            text(
                f"""
                SELECT
                    event_id,
                    tenant_id,
                    source,
                    event_type,
                    status,
                    occurred_at,
                    ingested_at
                FROM events
                WHERE {where_sql}
                ORDER BY ingested_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            params,
        )

        total = await session.execute(text(f"SELECT COUNT(*) AS total FROM events WHERE {where_sql}"), params)
        total_count = int(total.scalar_one() or 0)
        items = [dict(row._mapping) for row in rows]
        next_cursor = str(offset + limit) if offset + limit < total_count else None
        return {"items": items, "next_cursor": next_cursor, "total_estimate": total_count}

    @staticmethod
    async def fetch_event_detail(session: AsyncSession, event_id: UUID) -> dict | None:
        row = await session.execute(
            text(
                """
                SELECT
                    e.event_id,
                    e.tenant_id,
                    e.source,
                    e.event_type,
                    e.status,
                    e.payload,
                    e.features,
                    e.submitted_by,
                    e.occurred_at,
                    e.ingested_at
                FROM events e
                WHERE e.event_id = :event_id
                """
            ),
            {"event_id": str(event_id)},
        )
        event = row.first()
        if not event:
            return None

        processing = await session.execute(
            text(
                """
                SELECT
                    id,
                    model_name,
                    model_version,
                    anomaly_score,
                    threshold,
                    is_anomaly,
                    processed_at
                FROM anomaly_results
                WHERE event_id = :event_id
                ORDER BY processed_at ASC
                """
            ),
            {"event_id": str(event_id)},
        )
        return {
            **dict(event._mapping),
            "processing_history": [dict(item._mapping) for item in processing],
        }


class MonitoringRepository:
    SEVERITY_SQL = (
        "CASE "
        "WHEN ar.anomaly_score >= ar.threshold * 2 THEN 'critical' "
        "WHEN ar.anomaly_score >= ar.threshold * 1.5 THEN 'high' "
        "ELSE 'medium' END"
    )

    @staticmethod
    async def overview_metrics(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        from_ts: datetime,
        window_hours: int,
    ) -> dict:
        params: dict = {"from_ts": from_ts, "window_hours": max(1, window_hours)}
        tenant_events_clause = ""
        tenant_alerts_clause = ""
        if tenant_id:
            params["tenant_id"] = tenant_id
            tenant_events_clause = " AND e.tenant_id = :tenant_id "
            tenant_alerts_clause = " AND ev.tenant_id = :tenant_id "

        counts = await session.execute(
            text(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN e.status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_events,
                    COUNT(*) AS total_events
                FROM events e
                WHERE e.ingested_at >= :from_ts
                {tenant_events_clause}
                """
            ),
            params,
        )
        count_row = dict(counts.one()._mapping)

        anomalies = await session.execute(
            text(
                f"""
                SELECT COUNT(*) AS active_anomalies
                FROM anomaly_results ar
                JOIN events ev ON ev.event_id = ar.event_id
                WHERE ar.processed_at >= :from_ts
                {tenant_alerts_clause}
                """
            ),
            params,
        )
        active_anomalies = int(anomalies.scalar_one() or 0)

        total_events = int(count_row.get("total_events", 0) or 0)
        failed_events = int(count_row.get("failed_events", 0) or 0)
        failure_rate = (failed_events / total_events) if total_events else 0.0
        ingestion_rate = total_events / max(1, window_hours)
        alert_rate = active_anomalies / max(1, window_hours)

        model_health = max(0.0, min(100.0, (1.0 - (active_anomalies / max(1, total_events))) * 100))

        timeseries = await session.execute(
            text(
                f"""
                SELECT
                    date_trunc('hour', ar.processed_at) AS bucket,
                    AVG(ar.anomaly_score) AS avg_score,
                    AVG(ar.threshold) AS avg_threshold,
                    COUNT(*) AS anomaly_count
                FROM anomaly_results ar
                JOIN events ev ON ev.event_id = ar.event_id
                WHERE ar.processed_at >= :from_ts
                {tenant_alerts_clause}
                GROUP BY bucket
                ORDER BY bucket ASC
                """
            ),
            params,
        )

        severity = await session.execute(
            text(
                f"""
                SELECT
                    {MonitoringRepository.SEVERITY_SQL} AS severity,
                    COUNT(*) AS count
                FROM anomaly_results ar
                JOIN events ev ON ev.event_id = ar.event_id
                WHERE ar.processed_at >= :from_ts
                {tenant_alerts_clause}
                GROUP BY severity
                """
            ),
            params,
        )

        return {
            "active_anomalies": active_anomalies,
            "alert_rate": alert_rate,
            "ingestion_rate": ingestion_rate,
            "failure_rate": failure_rate,
            "model_health": model_health,
            "timeseries": [dict(row._mapping) for row in timeseries],
            "severity_distribution": [dict(row._mapping) for row in severity],
        }

    @staticmethod
    async def list_alerts(
        session: AsyncSession,
        *,
        tenant_id: str | None,
        severity: str | None,
        model_version: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
        score_min: float | None,
        score_max: float | None,
        cursor: str | None,
        limit: int,
    ) -> dict:
        try:
            offset = int(cursor or 0)
        except ValueError:
            offset = 0
        params: dict = {"offset": offset, "limit": limit}
        where_clauses = ["1=1"]

        if tenant_id:
            where_clauses.append("e.tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if model_version:
            where_clauses.append("ar.model_version = :model_version")
            params["model_version"] = model_version
        if from_ts:
            where_clauses.append("ar.processed_at >= :from_ts")
            params["from_ts"] = from_ts
        if to_ts:
            where_clauses.append("ar.processed_at <= :to_ts")
            params["to_ts"] = to_ts
        if score_min is not None:
            where_clauses.append("ar.anomaly_score >= :score_min")
            params["score_min"] = score_min
        if score_max is not None:
            where_clauses.append("ar.anomaly_score <= :score_max")
            params["score_max"] = score_max
        if severity:
            where_clauses.append(f"{MonitoringRepository.SEVERITY_SQL} = :severity")
            params["severity"] = severity

        where_sql = " AND ".join(where_clauses)
        rows = await session.execute(
            text(
                f"""
                SELECT
                    CONCAT('ar_', ar.id) AS alert_id,
                    ar.id AS numeric_alert_id,
                    ar.event_id,
                    e.tenant_id,
                    e.event_type,
                    e.source,
                    {MonitoringRepository.SEVERITY_SQL} AS severity,
                    ar.model_name,
                    ar.model_version,
                    ar.anomaly_score,
                    ar.threshold,
                    ar.processed_at AS created_at
                FROM anomaly_results ar
                JOIN events e ON e.event_id = ar.event_id
                WHERE {where_sql}
                ORDER BY ar.processed_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            params,
        )
        total = await session.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM anomaly_results ar
                JOIN events e ON e.event_id = ar.event_id
                WHERE {where_sql}
                """
            ),
            params,
        )
        total_count = int(total.scalar_one() or 0)
        items = [dict(row._mapping) for row in rows]
        next_cursor = str(offset + limit) if offset + limit < total_count else None
        return {"items": items, "next_cursor": next_cursor, "total_estimate": total_count}

    @staticmethod
    async def fetch_alert_detail(session: AsyncSession, alert_id: str) -> dict | None:
        normalized = alert_id.replace("ar_", "")
        if not normalized.isdigit():
            return None

        row = await session.execute(
            text(
                f"""
                SELECT
                    CONCAT('ar_', ar.id) AS alert_id,
                    ar.id AS numeric_alert_id,
                    ar.event_id,
                    e.tenant_id,
                    e.event_type,
                    e.source,
                    {MonitoringRepository.SEVERITY_SQL} AS severity,
                    ar.model_name,
                    ar.model_version,
                    ar.anomaly_score,
                    ar.threshold,
                    ar.is_anomaly,
                    ar.processed_at AS created_at,
                    e.payload AS event_payload,
                    e.status AS event_status,
                    e.occurred_at
                FROM anomaly_results ar
                JOIN events e ON e.event_id = ar.event_id
                WHERE ar.id = :alert_id
                """
            ),
            {"alert_id": int(normalized)},
        )
        item = row.first()
        if not item:
            return None
        return dict(item._mapping)


class ModelRepository:
    @staticmethod
    async def list_models(session: AsyncSession) -> list[dict]:
        rows = await session.execute(
            text(
                """
                SELECT
                    ar.model_name,
                    ar.model_version,
                    AVG(ar.threshold) AS threshold,
                    MAX(ar.processed_at) AS updated_at,
                    COUNT(*) AS inference_count,
                    AVG(CASE WHEN ar.is_anomaly THEN 1 ELSE 0 END) AS anomaly_rate
                FROM anomaly_results ar
                GROUP BY ar.model_name, ar.model_version
                ORDER BY updated_at DESC
                """
            )
        )
        return [dict(row._mapping) for row in rows]

    @staticmethod
    async def model_metrics(session: AsyncSession, model_version: str) -> dict:
        summary = await session.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_inferences,
                    AVG(CASE WHEN is_anomaly THEN 1 ELSE 0 END) AS anomaly_hit_rate
                FROM anomaly_results
                WHERE model_version = :model_version
                """
            ),
            {"model_version": model_version},
        )
        summary_row = dict(summary.one()._mapping)

        threshold_points = await session.execute(
            text(
                """
                SELECT
                    date_trunc('hour', processed_at) AS bucket,
                    AVG(threshold) AS avg_threshold,
                    AVG(anomaly_score) AS avg_score,
                    COUNT(*) AS volume
                FROM anomaly_results
                WHERE model_version = :model_version
                GROUP BY bucket
                ORDER BY bucket ASC
                """
            ),
            {"model_version": model_version},
        )

        return {
            "model_version": model_version,
            "anomaly_hit_rate": float(summary_row.get("anomaly_hit_rate") or 0.0),
            "total_inferences": int(summary_row.get("total_inferences") or 0),
            "inference_latency_ms": {"p50": None, "p95": None},
            "threshold_evolution": [dict(row._mapping) for row in threshold_points],
        }
