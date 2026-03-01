from functools import lru_cache

from risk_common.config import MLSettings


@lru_cache
def get_settings() -> MLSettings:
    return MLSettings()
