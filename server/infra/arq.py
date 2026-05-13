"""Arq queue settings shared by workers and queue health checks."""

from arq.connections import RedisSettings

import settings as S


def arq_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=S.REDIS_HOST,
        port=S.REDIS_PORT,
        password=S.REDIS_PASSWORD,
    )
