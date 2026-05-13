"""Dispatcher integration tests.

We exercise `dispatch_pending` directly with a stubbed ArqRedis pool and a
fresh in-memory database. The LISTEN/NOTIFY loop and signal plumbing are
covered indirectly — this test focuses on the contract every tick must
honour: at-least-once enqueue with `_job_id` dedup keyed off
``processor_id:event_id``.
"""

import asyncio
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base
from processors import dispatcher as dispatcher_module
from processors.registry import init_builtin_substrates
from services.file_events import create_file_event
from tests.factories.models import ProcessorFactory


@dataclass
class _EnqueuedJob:
    function: str
    args: tuple
    kwargs: dict


class FakeArqRedis:
    def __init__(self) -> None:
        self.enqueued: list[_EnqueuedJob] = []
        self._seen_job_ids: set[str] = set()

    async def enqueue_job(
        self, function: str, *args, _job_id: str | None = None, **kwargs
    ):
        if _job_id is not None:
            if _job_id in self._seen_job_ids:
                return None
            self._seen_job_ids.add(_job_id)
        self.enqueued.append(
            _EnqueuedJob(
                function=function,
                args=args,
                kwargs={**kwargs, "_job_id": _job_id},
            )
        )
        return object()


@pytest.fixture(autouse=True)
def _register_substrates() -> None:
    init_builtin_substrates()


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _seed_processor_with_events(session_factory, *, count: int):
    with session_factory() as db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        db.add(processor)
        db.flush()
        events = [
            create_file_event(
                db,
                event_type="file.created",
                file_id=uuid.uuid4(),
                payload={},
            )
            for _ in range(count)
        ]
        db.commit()
        return processor.id, [event.id for event in events]


def test_dispatch_pending_enqueues_one_job_per_processor(session_factory, monkeypatch):
    processor_id, event_ids = _seed_processor_with_events(session_factory, count=3)

    monkeypatch.setattr(dispatcher_module, "get_sessionmaker", lambda: session_factory)

    redis = FakeArqRedis()
    enqueued = asyncio.run(dispatcher_module.dispatch_pending(redis))

    assert enqueued == 1
    assert {job.kwargs["_job_id"] for job in redis.enqueued} == {
        f"{processor_id}:{event_ids[0]}"
    }


def test_dispatch_pending_dedups_via_job_id(session_factory, monkeypatch):
    processor_id, event_ids = _seed_processor_with_events(session_factory, count=2)

    monkeypatch.setattr(dispatcher_module, "get_sessionmaker", lambda: session_factory)

    redis = FakeArqRedis()
    asyncio.run(dispatcher_module.dispatch_pending(redis))
    asyncio.run(dispatcher_module.dispatch_pending(redis))

    assert len(redis.enqueued) == 1  # second tick is a no-op due to dedup


def test_dispatch_pending_skips_disabled_processor(session_factory, monkeypatch):
    with session_factory() as db:
        processor = ProcessorFactory.build(
            name="meta_extract",
            enabled=False,
            subscribed_event_types=["file.created"],
        )
        db.add(processor)
        db.flush()
        create_file_event(
            db, event_type="file.created", file_id=uuid.uuid4(), payload={}
        )
        db.commit()

    monkeypatch.setattr(dispatcher_module, "get_sessionmaker", lambda: session_factory)

    redis = FakeArqRedis()
    enqueued = asyncio.run(dispatcher_module.dispatch_pending(redis))

    assert enqueued == 0
    assert redis.enqueued == []
