"""Arq queue settings shared by workers and queue health checks."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING

from arq import create_pool
from arq.connections import RedisSettings

import settings as S

if TYPE_CHECKING:
    from arq.connections import ArqRedis

_arq_redis: ArqRedis | None = None
_arq_redis_lock = asyncio.Lock()


def arq_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=S.REDIS_HOST,
        port=S.REDIS_PORT,
        password=S.REDIS_PASSWORD,
    )


async def get_arq_redis() -> ArqRedis:
    """Return a shared Arq Redis pool (lazy init, reused across readiness probes)."""
    global _arq_redis
    if _arq_redis is not None:
        return _arq_redis

    async with _arq_redis_lock:
        if _arq_redis is None:
            _arq_redis = await create_pool(
                arq_redis_settings(),
                default_queue_name=S.MAINTENANCE_QUEUE_NAME,
            )
        return _arq_redis


async def close_arq_redis() -> None:
    global _arq_redis
    if _arq_redis is None:
        return
    redis = _arq_redis
    _arq_redis = None
    await _close_redis(redis)


async def _close_redis(redis: ArqRedis) -> None:
    close = getattr(redis, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def reset_arq_redis_for_tests() -> None:
    """Clear the cached pool without closing (test isolation only)."""
    global _arq_redis
    _arq_redis = None
