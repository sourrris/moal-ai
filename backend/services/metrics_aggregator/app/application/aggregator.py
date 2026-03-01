from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings

settings = get_settings()


class MetricsAggregator:
    def __init__(self, session_factory: async_sessionmaker, redis_client: Redis):
        self.session_factory = session_factory
        self.redis_client = redis_client
        self._task: asyncio.Task | None = None
        self._last_drift_bucket: datetime | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(max(10, settings.connector_poll_seconds))

    async def run_once(self) -> None:
        async with self.session_factory() as session:
            rows_1m = await session.execute(
                text(
                    """
                    WITH events_window AS (
                        SELECT tenant_id, COUNT(*) AS total_events
                        FROM events_v2
                        WHERE ingested_at >= date_trunc('minute', NOW()) - INTERVAL '1 minute'
                        GROUP BY tenant_id
                    ),
                    decisions_window AS (
                        SELECT
                            tenant_id,
                            COUNT(*) AS total_decisions,
                            COALESCE(AVG(risk_score), 0) AS avg_risk_score,
                            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY decision_latency_ms) AS p95_latency
                        FROM risk_decisions
                        WHERE created_at >= date_trunc('minute', NOW()) - INTERVAL '1 minute'
                        GROUP BY tenant_id
                    )
                    SELECT
                        COALESCE(e.tenant_id, d.tenant_id) AS tenant_id,
                        COALESCE(e.total_events, 0) AS total_events,
                        COALESCE(d.total_decisions, 0) AS total_alerts,
                        COALESCE(d.avg_risk_score, 0) AS avg_risk_score,
                        COALESCE(d.p95_latency, 0)::INT AS p95_latency
                    FROM events_window e
                    FULL OUTER JOIN decisions_window d ON d.tenant_id = e.tenant_id
                    """
                )
            )
            metrics_1m = [dict(row._mapping) for row in rows_1m]

            for metric in metrics_1m:
                await session.execute(
                    text(
                        """
                        INSERT INTO metrics_1m (
                            tenant_id,
                            bucket,
                            total_events,
                            total_alerts,
                            avg_risk_score,
                            p95_decision_latency_ms,
                            updated_at
                        ) VALUES (
                            :tenant_id,
                            date_trunc('minute', NOW()),
                            :total_events,
                            :total_alerts,
                            :avg_risk_score,
                            :p95_latency,
                            NOW()
                        )
                        ON CONFLICT (tenant_id, bucket)
                        DO UPDATE SET
                            total_events = EXCLUDED.total_events,
                            total_alerts = EXCLUDED.total_alerts,
                            avg_risk_score = EXCLUDED.avg_risk_score,
                            p95_decision_latency_ms = EXCLUDED.p95_decision_latency_ms,
                            updated_at = NOW()
                        """
                    ),
                    metric,
                )

            await session.execute(
                text(
                    """
                    INSERT INTO metrics_1h (
                        tenant_id,
                        bucket,
                        total_events,
                        total_alerts,
                        avg_risk_score,
                        p95_decision_latency_ms,
                        updated_at
                    )
                    SELECT
                        tenant_id,
                        date_trunc('hour', NOW()) AS bucket,
                        COUNT(*) FILTER (WHERE source = 'event') AS total_events,
                        COUNT(*) FILTER (WHERE source = 'decision' AND status IN ('high', 'critical')) AS total_alerts,
                        AVG(risk_score) FILTER (WHERE source = 'decision') AS avg_risk_score,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY decision_latency_ms) FILTER (WHERE source = 'decision')::INT AS p95_decision_latency_ms,
                        NOW()
                    FROM (
                        SELECT tenant_id, 'event'::text AS source, NULL::text AS status, NULL::double precision AS risk_score, NULL::int AS decision_latency_ms, ingested_at AS ts
                        FROM events_v2
                        WHERE ingested_at >= date_trunc('hour', NOW()) - INTERVAL '1 hour'
                        UNION ALL
                        SELECT tenant_id, 'decision'::text AS source, risk_level AS status, risk_score, decision_latency_ms, created_at AS ts
                        FROM risk_decisions
                        WHERE created_at >= date_trunc('hour', NOW()) - INTERVAL '1 hour'
                    ) unified
                    GROUP BY tenant_id
                    ON CONFLICT (tenant_id, bucket)
                    DO UPDATE SET
                        total_events = EXCLUDED.total_events,
                        total_alerts = EXCLUDED.total_alerts,
                        avg_risk_score = EXCLUDED.avg_risk_score,
                        p95_decision_latency_ms = EXCLUDED.p95_decision_latency_ms,
                        updated_at = NOW()
                    """
                )
            )
            await self._capture_drift_snapshots(session)

            await session.commit()

        for metric in metrics_1m:
            avg_risk = float(metric["avg_risk_score"] or 0.0)
            payload = {
                "tenant_id": metric["tenant_id"],
                "risk_score": avg_risk,
                "risk_level": "high" if avg_risk >= 0.65 else "medium",
                "decision_latency_ms": int(metric["p95_latency"] or 0),
                "total_events_1m": int(metric["total_events"] or 0),
                "total_alerts_1m": int(metric["total_alerts"] or 0),
                "processed_at": datetime.now(tz=UTC).isoformat(),
            }
            await self.redis_client.publish(settings.redis_metrics_channel, json.dumps(payload))

    async def _capture_drift_snapshots(self, session) -> None:
        now = datetime.now(tz=UTC)
        bucket = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        if self._last_drift_bucket == bucket:
            return
        self._last_drift_bucket = bucket

        rows = await session.execute(
            text(
                """
                WITH recent AS (
                    SELECT
                        tenant_id,
                        model_name,
                        model_version,
                        COUNT(*) AS recent_count,
                        AVG(ml_anomaly_score) AS recent_mean
                    FROM risk_decisions
                    WHERE created_at >= NOW() - INTERVAL '1 hour'
                    GROUP BY tenant_id, model_name, model_version
                ),
                baseline AS (
                    SELECT
                        tenant_id,
                        model_name,
                        model_version,
                        COUNT(*) AS baseline_count,
                        AVG(ml_anomaly_score) AS baseline_mean,
                        COALESCE(STDDEV_POP(ml_anomaly_score), 0.0) AS baseline_std
                    FROM risk_decisions
                    WHERE created_at >= NOW() - INTERVAL '24 hours'
                      AND created_at < NOW() - INTERVAL '1 hour'
                    GROUP BY tenant_id, model_name, model_version
                )
                SELECT
                    r.tenant_id,
                    r.model_name,
                    r.model_version,
                    r.recent_count,
                    r.recent_mean,
                    COALESCE(b.baseline_count, 0) AS baseline_count,
                    COALESCE(b.baseline_mean, 0.0) AS baseline_mean,
                    COALESCE(b.baseline_std, 0.0) AS baseline_std
                FROM recent r
                LEFT JOIN baseline b
                  ON b.tenant_id = r.tenant_id
                 AND b.model_name = r.model_name
                 AND b.model_version = r.model_version
                """
            )
        )

        for row in rows:
            data = dict(row._mapping)
            recent_count = int(data.get("recent_count") or 0)
            baseline_count = int(data.get("baseline_count") or 0)
            recent_mean = float(data.get("recent_mean") or 0.0)
            baseline_mean = float(data.get("baseline_mean") or 0.0)
            baseline_std = float(data.get("baseline_std") or 0.0)
            if recent_count < 30 or baseline_count < 100:
                continue

            denom = baseline_std if baseline_std > 1e-6 else 1e-6
            drift_score = abs(recent_mean - baseline_mean) / denom
            drift_status = "stable"
            if drift_score >= 3.0:
                drift_status = "critical"
            elif drift_score >= 2.0:
                drift_status = "degraded"

            await session.execute(
                text(
                    """
                    INSERT INTO drift_snapshots (
                        tenant_id,
                        model_name,
                        model_version,
                        drift_score,
                        drift_status,
                        details,
                        observed_at
                    ) VALUES (
                        :tenant_id,
                        :model_name,
                        :model_version,
                        :drift_score,
                        :drift_status,
                        CAST(:details AS JSONB),
                        NOW()
                    )
                    """
                ),
                {
                    "tenant_id": data.get("tenant_id"),
                    "model_name": data.get("model_name"),
                    "model_version": data.get("model_version"),
                    "drift_score": drift_score,
                    "drift_status": drift_status,
                    "details": json.dumps(
                        {
                            "bucket": bucket.isoformat(),
                            "recent_count": recent_count,
                            "baseline_count": baseline_count,
                            "recent_mean": recent_mean,
                            "baseline_mean": baseline_mean,
                            "baseline_std": baseline_std,
                        }
                    ),
                },
            )
