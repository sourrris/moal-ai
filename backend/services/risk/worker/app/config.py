from functools import lru_cache

from risk_common.config import WorkerSettings


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
