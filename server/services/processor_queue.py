"""Arq queue settings shared by warm and cold workers.

The dispatcher (``processors.dispatcher``) is the only producer for the
``relic:processing`` queue. File mutations write ``file_events`` rows; the
dispatcher turns those rows into ``run_processor_event`` jobs.
"""

from arq.connections import RedisSettings

import settings as S


def redis_settings() -> RedisSettings:
    return RedisSettings(
        host=S.REDIS_HOST,
        port=S.REDIS_PORT,
        password=S.REDIS_PASSWORD,
    )
