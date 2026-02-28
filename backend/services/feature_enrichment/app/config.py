from functools import lru_cache

from risk_common.config import FeatureEnrichmentSettings


@lru_cache
def get_settings() -> FeatureEnrichmentSettings:
    return FeatureEnrichmentSettings()
