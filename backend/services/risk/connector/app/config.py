from functools import lru_cache

from risk_common.config import DataConnectorSettings


@lru_cache
def get_settings() -> DataConnectorSettings:
    return DataConnectorSettings()
