"""Compute behavioral features from behavior events for the autoencoder.

v2: Enriched 16-dimensional features with per-user baseline context.
Backward compatible: compute_features() still returns 9-dim for existing models.
compute_features_v2() returns 16-dim with context-aware features.
"""

import math
from datetime import datetime
from typing import Any

from moal_common.schemas import BehaviorEventIngest


def compute_features(event: BehaviorEventIngest) -> list[float]:
    """Compute the original 9-dimensional feature vector (backward compat)."""
    return _base_features(event)


def compute_features_v2(event: BehaviorEventIngest, baseline: dict[str, Any] | None = None) -> list[float]:
    """Compute an enriched 16-dimensional feature vector using per-user baseline context.

    Features 0-8: same as v1 (time encoding, failed auth, session, rate, device, error).
    Features 9-15: context-aware signals derived from user baseline.

    Args:
        event: The incoming behavior event.
        baseline: A dict from the user_baselines table (or None if first event).
    """
    base = _base_features(event)
    ctx = _context_features(event, baseline)
    return base + ctx


def _base_features(event: BehaviorEventIngest) -> list[float]:
    """Original 9-dimensional feature vector."""
    occurred = event.occurred_at
    if not isinstance(occurred, datetime):
        occurred = datetime.fromisoformat(str(occurred))

    hour = occurred.hour
    day = occurred.weekday()

    hour_sin = math.sin(2 * math.pi * hour / 24.0)
    hour_cos = math.cos(2 * math.pi * hour / 24.0)
    day_sin = math.sin(2 * math.pi * day / 7.0)
    day_cos = math.cos(2 * math.pi * day / 7.0)

    request_count = max(event.request_count, 1)
    failed_auth_ratio = min(event.failed_auth_count / request_count, 1.0)

    duration = event.session_duration_seconds or 0
    session_duration_norm = min(duration / 28800.0, 1.0)

    if duration > 0:
        request_rate = min((request_count / (duration / 60.0)) / 100.0, 1.0)
    else:
        request_rate = min(request_count / 100.0, 1.0)

    is_new_device = 1.0 if event.device_fingerprint else 0.0

    status_error_rate = 1.0 if event.status_code and event.status_code >= 400 else 0.0

    return [
        hour_sin,
        hour_cos,
        day_sin,
        day_cos,
        failed_auth_ratio,
        session_duration_norm,
        request_rate,
        is_new_device,
        status_error_rate,
    ]


def _context_features(event: BehaviorEventIngest, baseline: dict[str, Any] | None) -> list[float]:
    """7 context-aware features derived from user baseline.

    Features:
         9: ip_novelty      — 1.0 if IP never seen, decays with frequency
        10: device_novelty   — 1.0 if device never seen, decays with frequency
        11: geo_novelty      — 1.0 if country never seen, decays with frequency
        12: hour_deviation   — how unusual is this hour for this user (0..1)
        13: time_since_last  — normalized gap since last event (capped at 1.0 for 24h+)
        14: velocity         — events in last hour, normalized (capped at 1.0 for 50+)
        15: anomaly_history  — ratio of past anomalies to total events (0..1)
    """
    if baseline is None:
        # First event for this user: moderate novelty, no history
        return [1.0, 1.0, 1.0, 0.5, 1.0, 0.0, 0.0]

    total_events = baseline.get("total_events", 0) or 0

    # IP novelty: 1.0 = never seen, decays as frequency increases
    ip_novelty = _novelty_score(event.source_ip, baseline.get("known_ips"))

    # Device novelty
    device_novelty = _novelty_score(event.device_fingerprint, baseline.get("known_devices"))

    # Geo novelty
    geo_novelty = _novelty_score(event.geo_country, baseline.get("known_countries"))

    # Hour deviation: how unusual is this hour for this user?
    occurred = event.occurred_at
    if not isinstance(occurred, datetime):
        occurred = datetime.fromisoformat(str(occurred))
    hour = occurred.hour
    hourly_counts = baseline.get("hourly_counts") or [0] * 24
    if isinstance(hourly_counts, list) and len(hourly_counts) == 24 and total_events > 0:
        hour_fraction = hourly_counts[hour] / max(total_events, 1)
        # Invert: low fraction = high deviation
        hour_deviation = max(0.0, min(1.0 - hour_fraction * 10.0, 1.0))
    else:
        hour_deviation = 0.5

    # Time since last event (normalized: 0 = just happened, 1.0 = 24h+ gap)
    last_event_at = baseline.get("last_event_at")
    if last_event_at and occurred.tzinfo is not None:
        if isinstance(last_event_at, str):
            from datetime import timezone
            try:
                last_event_at = datetime.fromisoformat(last_event_at)
            except ValueError:
                last_event_at = None
        if last_event_at is not None:
            if last_event_at.tzinfo is None:
                from datetime import timezone
                last_event_at = last_event_at.replace(tzinfo=timezone.utc)
            gap_seconds = max((occurred - last_event_at).total_seconds(), 0)
            time_since_last = min(gap_seconds / 86400.0, 1.0)  # cap at 24h
        else:
            time_since_last = 1.0
    else:
        time_since_last = 1.0

    # Velocity: events in last hour, normalized
    events_last_hour = baseline.get("events_last_hour", 0) or 0
    velocity = min(events_last_hour / 50.0, 1.0)

    # Anomaly history ratio
    total_anomalies = baseline.get("total_anomalies", 0) or 0
    anomaly_history = min(total_anomalies / max(total_events, 1), 1.0)

    return [
        ip_novelty,
        device_novelty,
        geo_novelty,
        hour_deviation,
        time_since_last,
        velocity,
        anomaly_history,
    ]


def _novelty_score(value: str | None, known_map: dict | list | None) -> float:
    """Compute novelty score: 1.0 = never seen, decays toward 0 with frequency."""
    if not value:
        return 0.5  # No data available, neutral

    if known_map is None:
        return 1.0  # No history, fully novel

    # Handle JSONB dict format: {"value": count, ...}
    if isinstance(known_map, dict):
        count = known_map.get(value, 0)
        if isinstance(count, (int, float)):
            if count <= 0:
                return 1.0
            # Exponential decay: 1 occurrence ~= 0.5, 5 ~= 0.07, 10 ~= 0.005
            return math.exp(-0.7 * count)
        return 1.0

    return 1.0


# Feature dimensions and names

FEATURE_DIM = 9  # v1 backward compat
FEATURE_DIM_V2 = 16

FEATURE_NAMES = [
    "hour_of_day_sin",
    "hour_of_day_cos",
    "day_of_week_sin",
    "day_of_week_cos",
    "failed_auth_ratio",
    "session_duration_norm",
    "request_rate",
    "is_new_device",
    "status_error_rate",
]

FEATURE_NAMES_V2 = FEATURE_NAMES + [
    "ip_novelty",
    "device_novelty",
    "geo_novelty",
    "hour_deviation",
    "time_since_last",
    "velocity",
    "anomaly_history",
]
