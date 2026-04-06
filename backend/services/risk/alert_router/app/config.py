from functools import lru_cache

from moal_common.config import AlertRouterSettings


@lru_cache
def get_settings() -> AlertRouterSettings:
    return AlertRouterSettings()
