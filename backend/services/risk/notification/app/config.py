from functools import lru_cache

from moal_common.config import NotificationSettings


@lru_cache
def get_settings() -> NotificationSettings:
    return NotificationSettings()
