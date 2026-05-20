"""Two-tier TTL cache: process memory, then Redis, then caller loads on miss."""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

from redis.exceptions import RedisError

from infra.redis.client import RedisClient, get_redis_client
from utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class _LocalEntry:
    expires_at: float
    value: bytes


class TieredCache:
    """Namespace-scoped cache with generation-based invalidation."""

    def __init__(self, namespace: str, *, redis: RedisClient | None = None) -> None:
        self._namespace = namespace
        self._redis = redis or get_redis_client()
        self._local: dict[str, _LocalEntry] = {}
        self._local_generation: int | None = None

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def _generation_key(self) -> str:
        return self._redis.key("cache", "gen", self._namespace)

    def get(self, key: str) -> bytes | None:
        generation = self._read_generation()
        local_key = self._local_key(generation, key)
        now = time.monotonic()

        entry = self._local.get(local_key)
        if entry is not None:
            if entry.expires_at > now:
                return entry.value
            self._local.pop(local_key, None)

        redis_key = self._redis_key(generation, key)
        try:
            value = self._redis.get(redis_key)
        except RedisError:
            return None
        if value is None:
            return None

        self._local[local_key] = _LocalEntry(expires_at=now + 1.0, value=value)
        return value

    def set(self, key: str, value: bytes, *, ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            ttl_seconds = 1
        generation = self._read_generation()
        local_key = self._local_key(generation, key)
        now = time.monotonic()
        self._local[local_key] = _LocalEntry(
            expires_at=now + ttl_seconds,
            value=value,
        )
        try:
            self._redis.set(
                self._redis_key(generation, key),
                value,
                ex=ttl_seconds,
            )
        except RedisError:
            pass

    def invalidate(self) -> None:
        try:
            generation = self._redis.incr(self._generation_key)
            self._local_generation = generation
        except RedisError:
            self._local_generation = (self._local_generation or 0) + 1
            log.warning(
                "tiered_cache_invalidate_redis_unavailable",
                namespace=self._namespace,
            )
        self._local.clear()

    def invalidate_key(self, key: str) -> None:
        generation = self._read_generation()
        self._local.pop(self._local_key(generation, key), None)
        try:
            self._redis.delete(self._redis_key(generation, key))
        except RedisError:
            pass

    def clear_local(self) -> None:
        self._local.clear()
        self._local_generation = None

    def _read_generation(self) -> int:
        try:
            raw = self._redis.get(self._generation_key)
            generation = int(raw) if raw is not None else 0
        except RedisError:
            generation = self._local_generation or 0
        self._local_generation = generation
        return generation

    def _local_key(self, generation: int, key: str) -> str:
        return f"{generation}:{key}"

    def _redis_key(self, generation: int, key: str) -> str:
        return self._redis.key("cache", self._namespace, str(generation), key)


@lru_cache
def get_tiered_cache(namespace: str) -> TieredCache:
    return TieredCache(namespace)


def clear_all_tiered_caches() -> None:
    for namespace in (
        "list_objects",
        "folder_tree",
        "folder_paths",
        "effective_permissions",
        "access_key_active",
    ):
        get_tiered_cache(namespace).invalidate()
