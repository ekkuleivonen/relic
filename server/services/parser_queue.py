import uuid

from arq import create_pool
from arq.connections import RedisSettings

import settings as S
from utils.logging import get_logger

log = get_logger(__name__)


def redis_settings() -> RedisSettings:
    return RedisSettings(
        host=S.REDIS_HOST,
        port=S.REDIS_PORT,
        password=S.REDIS_PASSWORD,
    )


async def enqueue_parse_file(file_id: uuid.UUID) -> None:
    redis = await create_pool(redis_settings(), default_queue_name=S.PARSER_QUEUE_NAME)
    try:
        await redis.enqueue_job("parse_file", str(file_id))
    finally:
        await redis.aclose()


async def enqueue_parse_file_best_effort(file_id: uuid.UUID) -> None:
    try:
        await enqueue_parse_file(file_id)
    except Exception as exc:  # noqa: BLE001 - queue outage must not fail ingest
        log.warning(
            "parser_enqueue_failed",
            file_id=str(file_id),
            error=str(exc),
        )
