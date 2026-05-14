"""Dispatcher integration tests.

We exercise `dispatch_pending` directly with a stubbed ArqRedis pool and a
fresh in-memory database. The LISTEN/NOTIFY loop and signal plumbing are
covered indirectly — this test focuses on the contract every tick must
honour: at-least-once enqueue with `_job_id` dedup keyed off
``processor_id:dispatch_generation:event_id``.
"""

import asyncio
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, Processor
from processors import dispatcher as dispatcher_module
from processors.registry import init_builtin_processors
from services.file_events import create_file_event
from tests.factories.models import FolderFactory, ProcessorFactory


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
def _register_processors() -> None:
    init_builtin_processors()


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
        f"{processor_id}:0:{event_ids[0]}"
    }
    assert redis.enqueued[0].args == (str(processor_id), "0", str(event_ids[0]))


def test_dispatch_pending_dedups_via_job_id(session_factory, monkeypatch):
    processor_id, event_ids = _seed_processor_with_events(session_factory, count=2)

    monkeypatch.setattr(dispatcher_module, "get_sessionmaker", lambda: session_factory)

    redis = FakeArqRedis()
    asyncio.run(dispatcher_module.dispatch_pending(redis))
    asyncio.run(dispatcher_module.dispatch_pending(redis))

    assert len(redis.enqueued) == 1  # second tick is a no-op due to dedup


def test_dispatch_pending_uses_generation_in_job_id_after_rewind(
    session_factory, monkeypatch
):
    processor_id, event_ids = _seed_processor_with_events(session_factory, count=1)
    monkeypatch.setattr(dispatcher_module, "get_sessionmaker", lambda: session_factory)

    redis = FakeArqRedis()
    asyncio.run(dispatcher_module.dispatch_pending(redis))

    with session_factory() as db:
        processor = db.get(Processor, processor_id)
        processor.dispatch_generation = 1
        db.commit()

    asyncio.run(dispatcher_module.dispatch_pending(redis))

    assert [job.kwargs["_job_id"] for job in redis.enqueued] == [
        f"{processor_id}:0:{event_ids[0]}",
        f"{processor_id}:1:{event_ids[0]}",
    ]


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


def test_dispatch_pending_filters_by_subscribed_event_types(
    session_factory, monkeypatch
):
    """A processor only sees events whose type is in its subscription.

    Unsubscribed events do not advance the cursor and never reach the worker.
    Lag reported as ``pending_count`` therefore stays consistent with the
    cursor model: a burst of unsubscribed events is genuinely no-op work.
    """

    with session_factory() as db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        db.add(processor)
        db.flush()
        create_file_event(
            db, event_type="file.deleted", file_id=uuid.uuid4(), payload={}
        )
        create_file_event(
            db, event_type="file.deleted", file_id=uuid.uuid4(), payload={}
        )
        subscribed = create_file_event(
            db, event_type="file.created", file_id=uuid.uuid4(), payload={}
        )
        db.commit()
        processor_id = processor.id
        expected_event_id = subscribed.id

    monkeypatch.setattr(dispatcher_module, "get_sessionmaker", lambda: session_factory)

    redis = FakeArqRedis()
    enqueued = asyncio.run(dispatcher_module.dispatch_pending(redis))

    assert enqueued == 1
    job = redis.enqueued[0]
    assert job.kwargs["_job_id"] == f"{processor_id}:0:{expected_event_id}"


def test_dispatch_pending_filters_by_folder_scope(session_factory, monkeypatch):
    with session_factory() as db:
        root = FolderFactory.build(name="")
        db.add(root)
        db.flush()
        in_scope_folder = FolderFactory.build(name="in-scope", parent_id=root.id)
        out_of_scope_folder = FolderFactory.build(
            name="out-of-scope", parent_id=root.id
        )
        db.add_all([in_scope_folder, out_of_scope_folder])
        db.flush()
        processor = ProcessorFactory.build(
            name="meta_extract",
            subscribed_event_types=["file.created"],
            folder_scopes=[
                {"folder_id": str(in_scope_folder.id), "cascade": False}
            ],
        )
        db.add(processor)
        db.flush()
        create_file_event(
            db,
            event_type="file.created",
            file_id=uuid.uuid4(),
            folder_id=out_of_scope_folder.id,
            payload={},
        )
        expected = create_file_event(
            db,
            event_type="file.created",
            file_id=uuid.uuid4(),
            folder_id=in_scope_folder.id,
            payload={},
        )
        db.commit()
        processor_id = processor.id
        expected_event_id = expected.id

    monkeypatch.setattr(dispatcher_module, "get_sessionmaker", lambda: session_factory)

    redis = FakeArqRedis()
    enqueued = asyncio.run(dispatcher_module.dispatch_pending(redis))

    assert enqueued == 1
    job = redis.enqueued[0]
    assert job.kwargs["_job_id"] == f"{processor_id}:0:{expected_event_id}"


def test_dispatch_pending_fan_out_across_processors(session_factory, monkeypatch):
    """Two processors with disjoint subscriptions each get their own next event."""

    with session_factory() as db:
        creator = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        deleter = ProcessorFactory.build(
            name="webhook_deletes", subscribed_event_types=["file.deleted"]
        )
        db.add_all([creator, deleter])
        db.flush()
        created = create_file_event(
            db, event_type="file.created", file_id=uuid.uuid4(), payload={}
        )
        deleted = create_file_event(
            db, event_type="file.deleted", file_id=uuid.uuid4(), payload={}
        )
        db.commit()
        expected = {
            f"{creator.id}:0:{created.id}",
            f"{deleter.id}:0:{deleted.id}",
        }

    monkeypatch.setattr(dispatcher_module, "get_sessionmaker", lambda: session_factory)

    redis = FakeArqRedis()
    enqueued = asyncio.run(dispatcher_module.dispatch_pending(redis))

    assert enqueued == 2
    assert {job.kwargs["_job_id"] for job in redis.enqueued} == expected
