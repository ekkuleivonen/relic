"""Shared Redis client with consistent key prefixing."""

from __future__ import annotations

from functools import lru_cache

import redis
from redis.exceptions import RedisError

import settings as S
from infra import metrics
from utils.logging import get_logger

log = get_logger(__name__)

_KEY_PREFIX = "relic"


class RedisClient:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def key(self, *parts: str) -> str:
        return ":".join((_KEY_PREFIX, *parts))

    def ping(self) -> bool:
        started_at = metrics.timer_start()
        try:
            return bool(self._client.ping())
        except RedisError as exc:
            log.warning("redis_ping_failed", error=str(exc))
            return False
        finally:
            metrics.observe_redis_command(command="ping", started_at=started_at)

    def get(self, key: str) -> bytes | None:
        started_at = metrics.timer_start()
        try:
            return self._client.get(key)
        except RedisError as exc:
            log.warning("redis_get_failed", key=key, error=str(exc))
            return None
        finally:
            metrics.observe_redis_command(command="get", started_at=started_at)

    def set(self, key: str, value: bytes, *, ex: int | None = None) -> None:
        started_at = metrics.timer_start()
        try:
            self._client.set(key, value, ex=ex)
        except RedisError as exc:
            log.warning("redis_set_failed", key=key, error=str(exc))
        finally:
            metrics.observe_redis_command(command="set", started_at=started_at)

    def delete(self, *keys: str) -> None:
        if not keys:
            return
        started_at = metrics.timer_start()
        try:
            self._client.delete(*keys)
        except RedisError as exc:
            log.warning("redis_delete_failed", keys=list(keys), error=str(exc))
        finally:
            metrics.observe_redis_command(command="delete", started_at=started_at)

    def incr(self, key: str) -> int:
        started_at = metrics.timer_start()
        try:
            return int(self._client.incr(key))
        except RedisError as exc:
            log.warning("redis_incr_failed", key=key, error=str(exc))
            raise
        finally:
            metrics.observe_redis_command(command="incr", started_at=started_at)


@lru_cache
def get_redis_client() -> RedisClient:
    pool = redis.ConnectionPool(
        host=S.REDIS_HOST,
        port=S.REDIS_PORT,
        password=S.REDIS_PASSWORD or None,
        decode_responses=False,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    return RedisClient(redis.Redis(connection_pool=pool))
