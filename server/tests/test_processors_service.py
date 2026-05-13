"""Unit tests for `services.processors`.

Covers CRUD, dispatch surfacing, the worker execute pipeline, and operator
actions. All tests run against an in-memory SQLite database.
"""

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from managers.exceptions import BadRequestError, ConflictError, ResourceNotFound
from models import (
    AuditEvent,
    Base,
    FileEvent,
    PROCESSOR_SOURCE_ADMIN,
    Processor,
)
from processors.registry import init_builtin_substrates
from services import processors as processor_service
from services.event_context import EventContext
from services.file_events import create_file_event
from tests.factories.models import (
    FileEventFactory,
    FolderFactory,
    ProcessorFactory,
    UserFactory,
)


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


@pytest.fixture()
def db_session(session_factory):
    with session_factory() as session:
        yield session


def _make_event(
    db,
    *,
    event_type: str = "file.created",
    file_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
) -> FileEvent:
    event = FileEventFactory.build(
        event_type=event_type,
        file_id=file_id or uuid.uuid4(),
        folder_id=folder_id,
        offset=None,
    )
    return create_file_event(
        db,
        event_type=event.event_type,
        file_id=event.file_id,
        folder_id=event.folder_id,
        payload={},
    )


def test_create_processor_uses_substrate_defaults(db_session):
    processor = processor_service.create_processor(
        db_session,
        name="meta_extract",
        kind="meta_extract",
    )

    assert processor.kind == "meta_extract"
    assert processor.subscribed_event_types == [
        "file.created",
        "file.updated",
        "file.copied",
        "file.renamed",
    ]
    assert processor.enabled is True
    assert processor.source == PROCESSOR_SOURCE_ADMIN
    assert processor.last_committed_offset == 0


def test_create_processor_rejects_duplicate_name(db_session):
    processor_service.create_processor(
        db_session, name="dup", kind="meta_extract"
    )
    with pytest.raises(ConflictError):
        processor_service.create_processor(
            db_session, name="dup", kind="meta_extract"
        )


def test_create_processor_rejects_unknown_kind(db_session):
    with pytest.raises(BadRequestError):
        processor_service.create_processor(
            db_session, name="x", kind="not_a_real_kind"
        )


def test_create_processor_rejects_invalid_event_type(db_session):
    with pytest.raises(BadRequestError):
        processor_service.create_processor(
            db_session,
            name="x",
            kind="meta_extract",
            subscribed_event_types=["file.bogus"],
        )


def test_create_processor_normalizes_folder_scopes(db_session):
    folder = FolderFactory.build()
    db_session.add(folder)
    db_session.flush()

    processor = processor_service.create_processor(
        db_session,
        name="scoped",
        kind="meta_extract",
        folder_scopes=[
            {"folder_id": str(folder.id), "cascade": False},
            {"folder_id": str(folder.id), "cascade": True},
        ],
    )

    assert processor.folder_scopes == [
        {"folder_id": str(folder.id), "cascade": True}
    ]


def test_create_processor_rejects_missing_folder_scope(db_session):
    with pytest.raises(ResourceNotFound):
        processor_service.create_processor(
            db_session,
            name="scoped",
            kind="meta_extract",
            folder_scopes=[{"folder_id": str(uuid.uuid4()), "cascade": True}],
        )


def test_upsert_seed_processor_is_idempotent(db_session):
    first = processor_service.upsert_seed_processor(
        db_session,
        name="meta_extract",
        kind="meta_extract",
        subscribed_event_types=["file.created"],
    )
    second = processor_service.upsert_seed_processor(
        db_session,
        name="meta_extract",
        kind="meta_extract",
        subscribed_event_types=["file.created", "file.updated"],
    )

    assert first.id == second.id
    assert second.subscribed_event_types == ["file.created", "file.updated"]


def test_update_processor_writes_audit_event(db_session):
    actor = UserFactory.build()
    db_session.add(actor)
    db_session.commit()
    processor = processor_service.create_processor(
        db_session, name="x", kind="meta_extract"
    )

    processor_service.update_processor(
        db_session,
        processor_id=processor.id,
        enabled=False,
        event_context=EventContext(actor_user_id=actor.id, request_id="req-1"),
    )

    refreshed = db_session.get(Processor, processor.id)
    assert refreshed.enabled is False

    audit = db_session.scalars(
        select(AuditEvent).where(AuditEvent.operation == "processor.disabled")
    ).one()
    assert audit.meta["changes"]["enabled"] == {"from": True, "to": False}


def test_update_seed_processor_rejects_config_drift(db_session):
    processor = processor_service.upsert_seed_processor(
        db_session, name="meta_extract", kind="meta_extract"
    )
    db_session.commit()

    with pytest.raises(BadRequestError):
        processor_service.update_processor(
            db_session,
            processor_id=processor.id,
            config={"unexpected": True},
        )


def test_create_processor_validates_config_for_kind(db_session):
    with pytest.raises(BadRequestError):
        processor_service.create_processor(
            db_session,
            name="x",
            kind="meta_extract",
            config={"unexpected": True},
        )


def test_delete_processor_blocks_seeded_rows(db_session):
    processor = processor_service.upsert_seed_processor(
        db_session, name="meta_extract", kind="meta_extract"
    )
    db_session.commit()
    with pytest.raises(BadRequestError):
        processor_service.delete_processor(
            db_session, processor_id=processor.id
        )


def test_collect_pending_jobs_returns_only_subscribed_events_past_cursor(db_session):
    processor = ProcessorFactory.build(
        name="meta_extract",
        last_committed_offset=0,
        subscribed_event_types=["file.created"],
    )
    db_session.add(processor)
    db_session.flush()

    in_scope = _make_event(db_session, event_type="file.created")
    _make_event(db_session, event_type="file.deleted")
    db_session.commit()

    jobs = processor_service.collect_pending_jobs(db_session)

    assert [job.event_id for job in jobs] == [in_scope.id]
    assert jobs[0].processor_id == processor.id


def test_collect_pending_jobs_respects_cursor(db_session):
    processor = ProcessorFactory.build(
        name="meta_extract",
        subscribed_event_types=["file.created"],
        last_committed_offset=0,
    )
    db_session.add(processor)
    db_session.flush()

    earlier = _make_event(db_session, event_type="file.created")
    later = _make_event(db_session, event_type="file.created")

    processor.last_committed_offset = earlier.offset
    db_session.commit()

    jobs = processor_service.collect_pending_jobs(db_session)
    assert [job.event_id for job in jobs] == [later.id]


def test_collect_pending_jobs_skips_disabled_processor(db_session):
    processor = ProcessorFactory.build(
        name="meta_extract",
        enabled=False,
        subscribed_event_types=["file.created"],
    )
    db_session.add(processor)
    db_session.flush()
    _make_event(db_session, event_type="file.created")
    db_session.commit()

    assert processor_service.collect_pending_jobs(db_session) == []


def test_collect_pending_jobs_filters_by_exact_folder_scope(db_session):
    root = FolderFactory.build(name="")
    db_session.add(root)
    db_session.flush()
    in_scope_folder = FolderFactory.build(name="in-scope", parent_id=root.id)
    out_of_scope_folder = FolderFactory.build(name="out-of-scope", parent_id=root.id)
    db_session.add_all([in_scope_folder, out_of_scope_folder])
    db_session.flush()
    processor = ProcessorFactory.build(
        name="meta_extract",
        subscribed_event_types=["file.created"],
        folder_scopes=[
            {"folder_id": str(in_scope_folder.id), "cascade": False}
        ],
    )
    db_session.add(processor)
    db_session.flush()

    _make_event(
        db_session, event_type="file.created", folder_id=out_of_scope_folder.id
    )
    in_scope = _make_event(
        db_session, event_type="file.created", folder_id=in_scope_folder.id
    )
    db_session.commit()

    jobs = processor_service.collect_pending_jobs(db_session)

    assert [job.event_id for job in jobs] == [in_scope.id]


def test_collect_pending_jobs_filters_by_cascading_folder_scope(db_session):
    root = FolderFactory.build(name="")
    db_session.add(root)
    db_session.flush()
    child = FolderFactory.build(name="child", parent_id=root.id)
    sibling = FolderFactory.build(name="sibling", parent_id=root.id)
    db_session.add_all([child, sibling])
    db_session.flush()
    grandchild = FolderFactory.build(name="grandchild", parent_id=child.id)
    db_session.add(grandchild)
    db_session.flush()
    processor = ProcessorFactory.build(
        name="meta_extract",
        subscribed_event_types=["file.created"],
        folder_scopes=[{"folder_id": str(child.id), "cascade": True}],
    )
    db_session.add(processor)
    db_session.flush()

    _make_event(db_session, event_type="file.created", folder_id=sibling.id)
    in_scope = _make_event(
        db_session, event_type="file.created", folder_id=grandchild.id
    )
    db_session.commit()

    jobs = processor_service.collect_pending_jobs(db_session)

    assert [job.event_id for job in jobs] == [in_scope.id]


def test_get_processor_with_lag_reports_pending(db_session):
    processor = ProcessorFactory.build(
        name="meta_extract", subscribed_event_types=["file.created"]
    )
    db_session.add(processor)
    db_session.flush()
    _make_event(db_session, event_type="file.created")
    _make_event(db_session, event_type="file.deleted")
    db_session.commit()

    info = processor_service.get_processor_with_lag(db_session, processor.id)
    assert info.pending_count == 1
    assert info.head_offset == 2


def test_get_processor_with_lag_respects_folder_scope(db_session):
    root = FolderFactory.build(name="")
    db_session.add(root)
    db_session.flush()
    in_scope_folder = FolderFactory.build(name="in-scope", parent_id=root.id)
    out_of_scope_folder = FolderFactory.build(name="out-of-scope", parent_id=root.id)
    db_session.add_all([in_scope_folder, out_of_scope_folder])
    db_session.flush()
    processor = ProcessorFactory.build(
        name="meta_extract",
        subscribed_event_types=["file.created"],
        folder_scopes=[
            {"folder_id": str(in_scope_folder.id), "cascade": False}
        ],
    )
    db_session.add(processor)
    db_session.flush()
    _make_event(
        db_session, event_type="file.created", folder_id=in_scope_folder.id
    )
    _make_event(
        db_session, event_type="file.created", folder_id=out_of_scope_folder.id
    )
    db_session.commit()

    info = processor_service.get_processor_with_lag(db_session, processor.id)
    assert info.pending_count == 1


def test_execute_processor_event_advances_cursor_on_success(
    session_factory, monkeypatch
):
    monkeypatch.setattr(
        "processors.meta_extract.base.parse_file", lambda db, file_id: None
    )

    with session_factory() as bootstrap_db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        event = _make_event(bootstrap_db, event_type="file.created")
        processor_id = processor.id
        event_id = event.id
        event_offset = event.offset
        bootstrap_db.commit()

    result = processor_service.execute_processor_event(
        session_factory,
        processor_id=processor_id,
        event_id=event_id,
    )

    assert result.status == "ok"
    assert result.advanced_to_offset == event_offset

    with session_factory() as verify_db:
        refreshed = verify_db.get(Processor, processor_id)
        assert refreshed.last_committed_offset == event_offset
        assert refreshed.last_committed_at is not None
        outcome = verify_db.scalars(
            select(FileEvent).where(
                FileEvent.event_type == "processor.meta_extract.completed"
            )
        ).one()
        assert outcome.payload["source_event_id"] == str(event_id)


def test_execute_processor_event_emits_failure_without_advancing(
    session_factory, monkeypatch
):
    def raise_exc(db, file_id):
        raise RuntimeError("boom")

    monkeypatch.setattr("processors.meta_extract.base.parse_file", raise_exc)

    with session_factory() as bootstrap_db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        event = _make_event(bootstrap_db, event_type="file.created")
        processor_id = processor.id
        event_id = event.id
        bootstrap_db.commit()

    result = processor_service.execute_processor_event(
        session_factory,
        processor_id=processor_id,
        event_id=event_id,
    )

    assert result.status == "failed"
    assert result.advanced_to_offset is None

    with session_factory() as verify_db:
        refreshed = verify_db.get(Processor, processor_id)
        assert refreshed.last_committed_offset == 0
        outcome = verify_db.scalars(
            select(FileEvent).where(
                FileEvent.event_type == "processor.meta_extract.failed"
            )
        ).one()
        assert outcome.status == "failed"
        assert outcome.payload["error_class"] == "RuntimeError"
        assert outcome.payload["error_message"] == "boom"
        assert refreshed.last_failed_event_id == event_id
        assert refreshed.last_failed_at is not None
        assert refreshed.last_error_class == "RuntimeError"
        assert refreshed.last_error_message == "boom"


def test_collect_pending_jobs_suppresses_stored_failed_event(
    session_factory, monkeypatch
):
    def raise_exc(db, file_id):
        raise RuntimeError("boom")

    monkeypatch.setattr("processors.meta_extract.base.parse_file", raise_exc)

    with session_factory() as bootstrap_db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        event = _make_event(bootstrap_db, event_type="file.created")
        processor_id = processor.id
        event_id = event.id
        bootstrap_db.commit()

    processor_service.execute_processor_event(
        session_factory,
        processor_id=processor_id,
        event_id=event_id,
    )

    with session_factory() as verify_db:
        assert processor_service.collect_pending_jobs(verify_db) == []


def test_execute_processor_event_skips_when_already_processed(
    session_factory, monkeypatch
):
    parse_calls: list[uuid.UUID] = []

    def handler(db, file_id):
        parse_calls.append(file_id)

    monkeypatch.setattr("processors.meta_extract.base.parse_file", handler)

    with session_factory() as bootstrap_db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        event = _make_event(bootstrap_db, event_type="file.created")
        processor.last_committed_offset = event.offset
        processor_id = processor.id
        event_id = event.id
        bootstrap_db.commit()

    result = processor_service.execute_processor_event(
        session_factory,
        processor_id=processor_id,
        event_id=event_id,
    )

    assert result.status == "skipped_already_processed"
    assert parse_calls == []


def test_execute_processor_event_refuses_non_subscribed(
    session_factory, monkeypatch
):
    """Workers refuse non-subscribed events instead of jumping the cursor.

    The dispatcher already filters on ``subscribed_event_types``, so reaching
    the worker with an event the processor wouldn't run can only happen if a
    stale enqueue races a subscription edit. We do not silently advance over
    work the new subscription wants — we no-op and let the next dispatcher
    tick refresh from the DB.
    """

    monkeypatch.setattr(
        "processors.meta_extract.base.parse_file", lambda db, file_id: None
    )

    with session_factory() as bootstrap_db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        event = _make_event(bootstrap_db, event_type="file.deleted")
        processor_id = processor.id
        event_id = event.id
        starting_cursor = processor.last_committed_offset
        bootstrap_db.commit()

    result = processor_service.execute_processor_event(
        session_factory,
        processor_id=processor_id,
        event_id=event_id,
    )

    assert result.status == "skipped_missing_event"
    assert result.advanced_to_offset is None
    with session_factory() as verify_db:
        refreshed = verify_db.get(Processor, processor_id)
        assert refreshed.last_committed_offset == starting_cursor


def test_execute_processor_event_refuses_folder_scope_mismatch(
    session_factory, monkeypatch
):
    monkeypatch.setattr(
        "processors.meta_extract.base.parse_file", lambda db, file_id: None
    )

    with session_factory() as bootstrap_db:
        root = FolderFactory.build(name="")
        bootstrap_db.add(root)
        bootstrap_db.flush()
        in_scope_folder = FolderFactory.build(name="in-scope", parent_id=root.id)
        out_of_scope_folder = FolderFactory.build(
            name="out-of-scope", parent_id=root.id
        )
        bootstrap_db.add_all([in_scope_folder, out_of_scope_folder])
        bootstrap_db.flush()
        processor = ProcessorFactory.build(
            name="meta_extract",
            subscribed_event_types=["file.created"],
            folder_scopes=[
                {"folder_id": str(in_scope_folder.id), "cascade": False}
            ],
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        event = _make_event(
            bootstrap_db,
            event_type="file.created",
            folder_id=out_of_scope_folder.id,
        )
        processor_id = processor.id
        event_id = event.id
        starting_cursor = processor.last_committed_offset
        bootstrap_db.commit()

    result = processor_service.execute_processor_event(
        session_factory,
        processor_id=processor_id,
        event_id=event_id,
    )

    assert result.status == "skipped_missing_event"
    assert result.advanced_to_offset is None
    with session_factory() as verify_db:
        refreshed = verify_db.get(Processor, processor_id)
        assert refreshed.last_committed_offset == starting_cursor


def test_rewind_cursor_writes_audit(db_session):
    actor = UserFactory.build()
    db_session.add(actor)
    db_session.commit()
    processor = ProcessorFactory.build(name="meta_extract", last_committed_offset=10)
    db_session.add(processor)
    db_session.commit()

    processor_service.rewind_cursor(
        db_session,
        processor_id=processor.id,
        target_offset=2,
        reason="reprocess after schema fix",
        event_context=EventContext(actor_user_id=actor.id, request_id="r"),
    )

    refreshed = db_session.get(Processor, processor.id)
    assert refreshed.last_committed_offset == 2
    audit = db_session.scalars(
        select(AuditEvent).where(AuditEvent.operation == "processor.cursor.rewound")
    ).one()
    assert audit.meta["from_offset"] == 10
    assert audit.meta["to_offset"] == 2
    assert audit.meta["reason"] == "reprocess after schema fix"


def test_rewind_cursor_rejects_negative(db_session):
    processor = ProcessorFactory.build(name="meta_extract")
    db_session.add(processor)
    db_session.commit()
    with pytest.raises(BadRequestError):
        processor_service.rewind_cursor(
            db_session,
            processor_id=processor.id,
            target_offset=-1,
            reason="bad offset",
        )


def test_rewind_cursor_rejects_forward_jump(db_session):
    processor = ProcessorFactory.build(name="meta_extract", last_committed_offset=1)
    db_session.add(processor)
    db_session.commit()
    with pytest.raises(BadRequestError):
        processor_service.rewind_cursor(
            db_session,
            processor_id=processor.id,
            target_offset=2,
            reason="unsafe forward jump",
        )


def test_rewind_cursor_requires_reason(db_session):
    processor = ProcessorFactory.build(name="meta_extract")
    db_session.add(processor)
    db_session.commit()
    with pytest.raises(BadRequestError):
        processor_service.rewind_cursor(
            db_session, processor_id=processor.id, target_offset=0, reason=""
        )


def test_skip_stuck_event_advances_and_audits(db_session):
    actor = UserFactory.build()
    db_session.add(actor)
    db_session.commit()
    processor = ProcessorFactory.build(
        name="meta_extract",
        subscribed_event_types=["file.created"],
        last_committed_offset=0,
    )
    db_session.add(processor)
    db_session.flush()
    event = _make_event(db_session, event_type="file.created")
    db_session.commit()

    processor_service.skip_stuck_event(
        db_session,
        processor_id=processor.id,
        event_id=event.id,
        reason="poison pill",
        event_context=EventContext(actor_user_id=actor.id, request_id="r"),
    )

    refreshed = db_session.get(Processor, processor.id)
    assert refreshed.last_committed_offset == event.offset

    # Skips are an admin intervention, not part of the content stream — they
    # only land in audit_events. External consumers must not see a synthetic
    # outcome event for an event the processor never actually ran.
    outcomes = db_session.scalars(
        select(FileEvent).where(FileEvent.event_type.like("processor.%"))
    ).all()
    assert outcomes == []

    audit = db_session.scalars(
        select(AuditEvent).where(AuditEvent.operation == "processor.cursor.skipped")
    ).one()
    assert audit.meta["skipped_event_id"] == str(event.id)
    assert audit.meta["reason"] == "poison pill"


def test_skip_stuck_event_rejects_already_processed(db_session):
    processor = ProcessorFactory.build(
        name="meta_extract", subscribed_event_types=["file.created"]
    )
    db_session.add(processor)
    db_session.flush()
    event = _make_event(db_session, event_type="file.created")
    processor.last_committed_offset = event.offset
    db_session.commit()

    with pytest.raises(BadRequestError):
        processor_service.skip_stuck_event(
            db_session,
            processor_id=processor.id,
            event_id=event.id,
            reason="already handled",
        )


def test_skip_stuck_event_rejects_non_next_event(db_session):
    processor = ProcessorFactory.build(
        name="meta_extract", subscribed_event_types=["file.created"]
    )
    db_session.add(processor)
    db_session.flush()
    _make_event(db_session, event_type="file.created")
    later = _make_event(db_session, event_type="file.created")
    db_session.commit()

    with pytest.raises(BadRequestError):
        processor_service.skip_stuck_event(
            db_session,
            processor_id=processor.id,
            event_id=later.id,
            reason="range skip should be rejected",
        )


def test_skip_stuck_event_requires_event(db_session):
    processor = ProcessorFactory.build(name="meta_extract")
    db_session.add(processor)
    db_session.commit()
    with pytest.raises(ResourceNotFound):
        processor_service.skip_stuck_event(
            db_session,
            processor_id=processor.id,
            event_id=uuid.uuid4(),
            reason="missing event",
        )


def test_skip_stuck_event_requires_reason(db_session):
    processor = ProcessorFactory.build(name="meta_extract")
    db_session.add(processor)
    db_session.flush()
    event = _make_event(db_session, event_type="file.created")
    db_session.commit()
    with pytest.raises(BadRequestError):
        processor_service.skip_stuck_event(
            db_session, processor_id=processor.id, event_id=event.id, reason=""
        )


def test_execute_processor_event_skips_disabled(session_factory):
    with session_factory() as bootstrap_db:
        processor = ProcessorFactory.build(
            name="meta_extract", enabled=False, subscribed_event_types=["file.created"]
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        event = _make_event(bootstrap_db, event_type="file.created")
        processor_id = processor.id
        event_id = event.id
        bootstrap_db.commit()

    result = processor_service.execute_processor_event(
        session_factory, processor_id=processor_id, event_id=event_id
    )
    assert result.status == "skipped_disabled"


def test_execute_processor_event_double_run_emits_outcome_once(
    session_factory, monkeypatch
):
    """Two concurrent workers must not emit duplicate completion events."""

    monkeypatch.setattr(
        "processors.meta_extract.base.parse_file", lambda db, file_id: None
    )

    with session_factory() as bootstrap_db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.created"]
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        event = _make_event(bootstrap_db, event_type="file.created")
        processor_id = processor.id
        event_id = event.id
        bootstrap_db.commit()

    first = processor_service.execute_processor_event(
        session_factory, processor_id=processor_id, event_id=event_id
    )
    second = processor_service.execute_processor_event(
        session_factory, processor_id=processor_id, event_id=event_id
    )

    assert first.status == "ok"
    assert second.status == "skipped_already_processed"

    with session_factory() as verify_db:
        outcomes = verify_db.scalars(
            select(FileEvent).where(
                FileEvent.event_type == "processor.meta_extract.completed"
            )
        ).all()
        assert len(outcomes) == 1


def test_meta_extract_runs_on_rename(session_factory, monkeypatch):
    parsed: list[uuid.UUID] = []

    def fake_parse(db, file_id):
        parsed.append(file_id)

    monkeypatch.setattr(
        "processors.meta_extract.base.parse_file", fake_parse
    )

    with session_factory() as bootstrap_db:
        processor = ProcessorFactory.build(
            name="meta_extract", subscribed_event_types=["file.renamed"]
        )
        bootstrap_db.add(processor)
        bootstrap_db.flush()
        file_id = uuid.uuid4()
        event = create_file_event(
            bootstrap_db,
            event_type="file.renamed",
            file_id=file_id,
            payload={"from_name": "old.txt", "to_name": "new.txt"},
        )
        bootstrap_db.commit()
        processor_id = processor.id
        event_id = event.id

    processor_service.execute_processor_event(
        session_factory, processor_id=processor_id, event_id=event_id
    )

    assert parsed == [file_id]
