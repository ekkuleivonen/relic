"""Shared Arq Redis pool lifecycle tests."""

from __future__ import annotations

import asyncio

import pytest

import infra.arq as arq_module
from infra.arq import close_arq_redis, get_arq_redis, reset_arq_redis_for_tests


class _FakeArqRedis:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_arq_pool():
    reset_arq_redis_for_tests()
    yield
    reset_arq_redis_for_tests()


def test_get_arq_redis_reuses_cached_pool(monkeypatch):
    created: list[_FakeArqRedis] = []

    async def fake_create_pool(*args, **kwargs):
        del args, kwargs
        pool = _FakeArqRedis()
        created.append(pool)
        return pool

    monkeypatch.setattr(arq_module, "create_pool", fake_create_pool)

    async def run() -> None:
        first = await get_arq_redis()
        second = await get_arq_redis()
        assert first is second

    asyncio.run(run())
    assert len(created) == 1


def test_close_arq_redis_closes_and_clears_pool(monkeypatch):
    fake = _FakeArqRedis()

    async def fake_create_pool(*args, **kwargs):
        del args, kwargs
        return fake

    monkeypatch.setattr(arq_module, "create_pool", fake_create_pool)

    async def run() -> None:
        await get_arq_redis()
        await close_arq_redis()

    asyncio.run(run())
    assert fake.closed is True
    assert arq_module._arq_redis is None


def test_check_redis_queues_uses_shared_pool(monkeypatch):
    import infra.health as health

    ping_count = 0
    fake = _FakeArqRedis()

    async def fake_get_arq_redis():
        return fake

    async def fake_ping():
        nonlocal ping_count
        ping_count += 1

    async def fake_zcard(_queue_name):
        return 0

    async def fake_zrange(*args, **kwargs):
        del args, kwargs
        return []

    fake.ping = fake_ping
    fake.zcard = fake_zcard
    fake.zrange = fake_zrange

    monkeypatch.setattr(health, "get_arq_redis", fake_get_arq_redis)

    async def run() -> None:
        await health.check_redis_queues()
        await health.check_redis_queues()

    asyncio.run(run())
    assert ping_count == 2
