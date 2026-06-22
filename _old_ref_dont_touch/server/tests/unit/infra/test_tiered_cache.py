"""Unit tests for the two-tier cache."""

from __future__ import annotations

import pytest

from infra.cache.tiered import TieredCache
from infra.redis.client import RedisClient


class FakeRedisBackend:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def set(self, key: str, value: bytes, *, ex: int | None = None) -> None:
        del ex
        self.values[key] = value

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)

    def incr(self, key: str) -> int:
        current = int(self.values.get(key, b"0"))
        new_value = current + 1
        self.values[key] = str(new_value).encode("ascii")
        return new_value


@pytest.fixture()
def fake_redis() -> FakeRedisBackend:
    return FakeRedisBackend()


@pytest.fixture()
def cache(fake_redis: FakeRedisBackend) -> TieredCache:
    return TieredCache("test", redis=RedisClient(fake_redis))  # type: ignore[arg-type]


def test_get_set_round_trip(cache: TieredCache) -> None:
    cache.set("alpha", b"payload", ttl_seconds=30)
    assert cache.get("alpha") == b"payload"


def test_invalidate_clears_local_and_bumps_generation(
    cache: TieredCache, fake_redis: FakeRedisBackend
) -> None:
    cache.set("alpha", b"payload", ttl_seconds=30)
    cache.invalidate()

    assert cache.get("alpha") is None
    assert int(fake_redis.values[cache._generation_key]) == 1


def test_second_process_sees_invalidated_generation(
    fake_redis: FakeRedisBackend,
) -> None:
    first = TieredCache("test", redis=RedisClient(fake_redis))  # type: ignore[arg-type]
    second = TieredCache("test", redis=RedisClient(fake_redis))  # type: ignore[arg-type]

    first.set("alpha", b"payload", ttl_seconds=30)
    first.invalidate()

    assert second.get("alpha") is None
