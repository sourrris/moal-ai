"""Compute real behavioral features from behavior events for the autoencoder."""

import math
from datetime import datetime

from moal_common.schemas import BehaviorEventIngest


def compute_features(event: BehaviorEventIngest) -> list[float]:
    """Compute a 9-dimensional feature vector from a behavior event.

    Features:
        0: hour_of_day_sin  — cyclical encoding of hour
        1: hour_of_day_cos
        2: day_of_week_sin  — cyclical encoding of day
        3: day_of_week_cos
        4: failed_auth_ratio — failed_auth_count / max(request_count, 1)
        5: session_duration_norm — normalized session duration (capped at 1.0)
        6: request_rate — requests per minute, normalized (capped at 1.0)
        7: is_new_device — 1.0 if device_fingerprint is present (novelty checked at caller)
        8: status_error_rate — 1.0 if status >= 400, else 0.0
    """
    occurred = event.occurred_at
    if not isinstance(occurred, datetime):
        occurred = datetime.fromisoformat(str(occurred))

    hour = occurred.hour
    day = occurred.weekday()

    # Cyclical encoding of time features
    hour_sin = math.sin(2 * math.pi * hour / 24.0)
    hour_cos = math.cos(2 * math.pi * hour / 24.0)
    day_sin = math.sin(2 * math.pi * day / 7.0)
    day_cos = math.cos(2 * math.pi * day / 7.0)

    # Failed auth ratio
    request_count = max(event.request_count, 1)
    failed_auth_ratio = min(event.failed_auth_count / request_count, 1.0)

    # Session duration normalized (cap at 8 hours = 28800 seconds)
    duration = event.session_duration_seconds or 0
    session_duration_norm = min(duration / 28800.0, 1.0)

    # Request rate: requests per minute of session, normalized (cap at 100 rpm)
    if duration > 0:
        request_rate = min((request_count / (duration / 60.0)) / 100.0, 1.0)
    else:
        request_rate = min(request_count / 100.0, 1.0)

    # Device fingerprint novelty (basic: 1.0 if fingerprint present, 0.0 if not)
    # Full novelty detection requires historical lookup, done at ingestion time
    is_new_device = 1.0 if event.device_fingerprint else 0.0

    # HTTP error rate
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


FEATURE_DIM = 9
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
