from functools import lru_cache

from risk_common.config import MetricsAggregatorSettings


@lru_cache
def get_settings() -> MetricsAggregatorSettings:
    return MetricsAggregatorSettings()
