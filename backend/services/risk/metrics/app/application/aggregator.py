from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings

settings = get_settings()


MIN_RECENT_DRIFT_DECISIONS = 30
MIN_BASELINE_DRIFT_DECISIONS = 100
MIN_RECENT_FEATURE_SAMPLES = 10
MIN_BASELINE_FEATURE_SAMPLES = 30
MAX_FEATURE_DRIFT_CONTRIBUTORS = 5


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _drift_status_for_score(score: float) -> str:
    if score >= 3.0:
        return "critical"
    if score >= 2.0:
        return "degraded"
    return "stable"


def _build_feature_distribution_snapshots(rows: list[dict], bucket: datetime) -> list[dict]:
    grouped: dict[tuple[str | None, str, str], dict] = {}
    for row in rows:
        tenant_id = row.get("tenant_id")
        model_name = str(row.get("model_name") or "")
        model_version = str(row.get("model_version") or "")
        feature_idx = int(row.get("feature_idx") or 0)
        key = (tenant_id, model_name, model_version)
        group = grouped.setdefault(
            key,
            {
                "tenant_id": tenant_id,
                "model_name": model_name,
                "model_version": model_version,
                "recent_decision_count": int(row.get("recent_decision_count") or 0),
                "baseline_decision_count": int(row.get("baseline_decision_count") or 0),
                "contributors": [],
                "baseline_source": "window_baseline",
            },
        )
        group["recent_decision_count"] = max(
            int(group["recent_decision_count"]),
            int(row.get("recent_decision_count") or 0),
        )
        group["baseline_decision_count"] = max(
            int(group["baseline_decision_count"]),
            int(row.get("baseline_decision_count") or 0),
        )

        recent_feature_count = int(row.get("recent_feature_count") or 0)
        recent_mean = _as_float(row.get("recent_mean"))
        recent_std = _as_float(row.get("recent_std"))
        training_mean = row.get("training_mean")
        training_std = row.get("training_std")
        training_sample_count = int(row.get("training_sample_count") or 0)

        baseline_feature_count = int(row.get("baseline_feature_count") or 0)
        baseline_mean = _as_float(row.get("baseline_mean"))
        baseline_std = _as_float(row.get("baseline_std"))
        baseline_source = "window_baseline"

        has_training_baseline = (
            isinstance(training_mean, list)
            and isinstance(training_std, list)
            and 0 <= feature_idx < len(training_mean)
            and 0 <= feature_idx < len(training_std)
        )
        if has_training_baseline:
            candidate_std = _as_float(training_std[feature_idx], default=0.0)
            if candidate_std > 0:
                baseline_mean = _as_float(training_mean[feature_idx])
                baseline_std = candidate_std
                baseline_feature_count = max(baseline_feature_count, training_sample_count)
                group["baseline_decision_count"] = max(int(group["baseline_decision_count"]), training_sample_count)
                group["baseline_source"] = "training_preprocessing"
                baseline_source = "training_preprocessing"

        if recent_feature_count < MIN_RECENT_FEATURE_SAMPLES or baseline_feature_count < MIN_BASELINE_FEATURE_SAMPLES:
            continue

        denom = baseline_std if baseline_std > 1e-6 else 1e-6
        mean_shift = abs(recent_mean - baseline_mean)
        mean_z = mean_shift / denom
        std_shift = abs(recent_std - baseline_std) / denom
        contributor_score = (0.7 * mean_z) + (0.3 * std_shift)

        group["contributors"].append(
            {
                "feature_index": feature_idx,
                "recent_feature_count": recent_feature_count,
                "baseline_feature_count": baseline_feature_count,
                "recent_mean": recent_mean,
                "baseline_mean": baseline_mean,
                "recent_std": recent_std,
                "baseline_std": baseline_std,
                "baseline_source": baseline_source,
                "mean_shift": mean_shift,
                "mean_shift_z": mean_z,
                "std_shift_ratio": std_shift,
                "score": contributor_score,
            }
        )

    snapshots: list[dict] = []
    for group in grouped.values():
        if (
            int(group["recent_decision_count"]) < MIN_RECENT_DRIFT_DECISIONS
            or int(group["baseline_decision_count"]) < MIN_BASELINE_DRIFT_DECISIONS
        ):
            continue
        contributors = sorted(
            list(group["contributors"]),
            key=lambda item: float(item["score"]),
            reverse=True,
        )
        if not contributors:
            continue

        top_contributors = contributors[:MAX_FEATURE_DRIFT_CONTRIBUTORS]
        drift_score = sum(float(item["score"]) for item in top_contributors) / len(top_contributors)
        snapshots.append(
            {
                "tenant_id": group["tenant_id"],
                "model_name": group["model_name"],
                "model_version": group["model_version"],
                "drift_score": drift_score,
                "drift_status": _drift_status_for_score(drift_score),
                "details": {
                    "bucket": bucket.isoformat(),
                    "method": "feature_distribution_shift",
                    "recent_decision_count": int(group["recent_decision_count"]),
                    "baseline_decision_count": int(group["baseline_decision_count"]),
                    "baseline_source": str(group["baseline_source"]),
                    "feature_count_evaluated": len(contributors),
                    "top_contributors": top_contributors,
                },
            }
        )
    return snapshots


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
                WITH recent_models AS (
                    SELECT
                        tenant_id,
                        model_name,
                        model_version,
                        COUNT(*) AS recent_decision_count
                    FROM risk_decisions
                    WHERE created_at >= NOW() - INTERVAL '1 hour'
                      AND array_length(feature_vector, 1) IS NOT NULL
                    GROUP BY tenant_id, model_name, model_version
                ),
                baseline_models AS (
                    SELECT
                        tenant_id,
                        model_name,
                        model_version,
                        COUNT(*) AS baseline_decision_count
                    FROM risk_decisions
                    WHERE created_at >= NOW() - INTERVAL '24 hours'
                      AND created_at < NOW() - INTERVAL '1 hour'
                      AND array_length(feature_vector, 1) IS NOT NULL
                    GROUP BY tenant_id, model_name, model_version
                ),
                recent_expanded AS (
                    SELECT
                        rd.tenant_id,
                        rd.model_name,
                        rd.model_version,
                        (fv.ordinality - 1)::INT AS feature_idx,
                        fv.value::DOUBLE PRECISION AS feature_value
                    FROM risk_decisions rd
                    CROSS JOIN LATERAL unnest(rd.feature_vector) WITH ORDINALITY AS fv(value, ordinality)
                    WHERE rd.created_at >= NOW() - INTERVAL '1 hour'
                      AND array_length(rd.feature_vector, 1) IS NOT NULL
                ),
                baseline_expanded AS (
                    SELECT
                        rd.tenant_id,
                        rd.model_name,
                        rd.model_version,
                        (fv.ordinality - 1)::INT AS feature_idx,
                        fv.value::DOUBLE PRECISION AS feature_value
                    FROM risk_decisions rd
                    CROSS JOIN LATERAL unnest(rd.feature_vector) WITH ORDINALITY AS fv(value, ordinality)
                    WHERE rd.created_at >= NOW() - INTERVAL '24 hours'
                      AND rd.created_at < NOW() - INTERVAL '1 hour'
                      AND array_length(rd.feature_vector, 1) IS NOT NULL
                ),
                recent_stats AS (
                    SELECT
                        tenant_id,
                        model_name,
                        model_version,
                        feature_idx,
                        COUNT(*) AS recent_feature_count,
                        AVG(feature_value) AS recent_mean,
                        COALESCE(STDDEV_POP(feature_value), 0.0) AS recent_std
                    FROM recent_expanded
                    GROUP BY tenant_id, model_name, model_version, feature_idx
                ),
                baseline_stats AS (
                    SELECT
                        tenant_id,
                        model_name,
                        model_version,
                        feature_idx,
                        COUNT(*) AS baseline_feature_count,
                        AVG(feature_value) AS baseline_mean,
                        COALESCE(STDDEV_POP(feature_value), 0.0) AS baseline_std
                    FROM baseline_expanded
                    GROUP BY tenant_id, model_name, model_version, feature_idx
                ),
                latest_training_runs AS (
                    SELECT
                        model_name,
                        model_version,
                        metrics,
                        ROW_NUMBER() OVER (
                            PARTITION BY model_name, model_version
                            ORDER BY finished_at DESC NULLS LAST, started_at DESC
                        ) AS rn
                    FROM model_training_runs
                    WHERE status = 'success'
                      AND model_version IS NOT NULL
                ),
                training_baselines AS (
                    SELECT
                        model_name,
                        model_version,
                        metrics->'preprocessing'->'mean' AS training_mean,
                        metrics->'preprocessing'->'std' AS training_std,
                        COALESCE((metrics->>'sample_count')::INT, 0) AS training_sample_count
                    FROM latest_training_runs
                    WHERE rn = 1
                )
                SELECT
                    rs.tenant_id,
                    rs.model_name,
                    rs.model_version,
                    rs.feature_idx,
                    rs.recent_feature_count,
                    rs.recent_mean,
                    rs.recent_std,
                    COALESCE(bs.baseline_feature_count, 0) AS baseline_feature_count,
                    COALESCE(bs.baseline_mean, 0.0) AS baseline_mean,
                    COALESCE(bs.baseline_std, 0.0) AS baseline_std,
                    rm.recent_decision_count,
                    COALESCE(bm.baseline_decision_count, 0) AS baseline_decision_count,
                    tb.training_mean,
                    tb.training_std,
                    COALESCE(tb.training_sample_count, 0) AS training_sample_count
                FROM recent_stats rs
                JOIN recent_models rm
                  ON rm.tenant_id = rs.tenant_id
                 AND rm.model_name = rs.model_name
                 AND rm.model_version = rs.model_version
                LEFT JOIN baseline_stats bs
                  ON bs.tenant_id = rs.tenant_id
                 AND bs.model_name = rs.model_name
                 AND bs.model_version = rs.model_version
                 AND bs.feature_idx = rs.feature_idx
                LEFT JOIN baseline_models bm
                  ON bm.tenant_id = rs.tenant_id
                 AND bm.model_name = rs.model_name
                 AND bm.model_version = rs.model_version
                LEFT JOIN training_baselines tb
                  ON tb.model_name = rs.model_name
                 AND tb.model_version = rs.model_version
                """
            )
        )
        row_payloads = [dict(row._mapping) for row in rows]
        snapshots = _build_feature_distribution_snapshots(row_payloads, bucket)

        for snapshot in snapshots:
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
                    "tenant_id": snapshot["tenant_id"],
                    "model_name": snapshot["model_name"],
                    "model_version": snapshot["model_version"],
                    "drift_score": snapshot["drift_score"],
                    "drift_status": snapshot["drift_status"],
                    "details": json.dumps(snapshot["details"]),
                },
            )
