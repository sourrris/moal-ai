from functools import lru_cache

from moal_common.config import ApiGatewaySettings


@lru_cache
def get_settings() -> ApiGatewaySettings:
    return ApiGatewaySettings()
