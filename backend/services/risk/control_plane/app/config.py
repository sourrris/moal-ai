from functools import lru_cache

from moal_common.config import ControlPlaneSettings


@lru_cache
def get_settings() -> ControlPlaneSettings:
    return ControlPlaneSettings()
