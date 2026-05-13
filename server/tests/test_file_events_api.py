import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from models import Base, FileEvent, Processor
from schema_plan import UserRole
from services.auth import create_session_token
from services.file_events import create_file_event, trim_file_events_older_than
from tests.factories.models import FileEventFactory, UserFactory


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def admin(db_session):
    admin = UserFactory.build(
        name="Admin", email="admin@relic.local", role=UserRole.ADMIN
    )
    db_session.add(admin)
    db_session.commit()
    return admin


@pytest.fixture()
def client(db_session, admin):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(admin))
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_list_file_events_returns_highest_offsets_first(client, db_session, admin):
    older = FileEventFactory.build(
        offset=1,
        event_type="file.created",
        actor_user_id=admin.id,
        request_id="req-old",
        file_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        payload={"name": "old.txt"},
    )
    newer = FileEventFactory.build(
        offset=2,
        event_type="file.deleted",
        actor_user_id=admin.id,
        request_id="req-new",
        file_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        payload={"name": "new.txt"},
    )
    db_session.add_all([older, newer])
    db_session.commit()

    response = client.get("/api/file-events/")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [item["request_id"] for item in body["items"]] == ["req-new", "req-old"]
    assert body["items"][0]["actor"]["email"] == "admin@relic.local"
    assert body["items"][0]["payload"] == {"name": "new.txt"}


def test_list_file_events_filters_and_paginates(client, db_session, admin):
    db_session.add_all(
        [
            FileEventFactory.build(
                offset=1,
                event_type="file.created",
                actor_user_id=admin.id,
                request_id="req-created-1",
            ),
            FileEventFactory.build(
                offset=2,
                event_type="file.deleted",
                actor_user_id=admin.id,
                request_id="req-deleted-1",
            ),
            FileEventFactory.build(
                offset=3,
                event_type="file.created",
                actor_user_id=admin.id,
                request_id="req-created-2",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/file-events/",
        params={"event_type": "file.created", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["event_type"] == "file.created"
    assert body["items"][0]["request_id"] == "req-created-2"


def test_list_file_events_rejects_invalid_status(client):
    response = client.get("/api/file-events/", params={"status": "maybe"})

    assert response.status_code == 400
    assert response.json()["detail"] == "status must be one of ['failed', 'succeeded']"


def test_clear_file_events_requires_admin(db_session):
    user = UserFactory.build(role=UserRole.USER)
    db_session.add(user)
    db_session.add(FileEventFactory.build())
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(user))
            response = test_client.delete("/api/file-events/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert len(db_session.scalars(select(FileEvent)).all()) == 1


def test_clear_file_events_rejects_pending_processor_events(client, db_session):
    db_session.add(
        Processor(
            name="meta_extract",
            kind="meta_extract",
            enabled=True,
            source="seed",
            subscribed_event_types=["file.created"],
            config={},
            last_committed_offset=0,
        )
    )
    db_session.add(FileEventFactory.build(offset=1, event_type="file.created"))
    db_session.commit()

    response = client.delete("/api/file-events/")

    assert response.status_code == 400
    assert len(db_session.scalars(select(FileEvent)).all()) == 1


def test_create_file_event_assigns_monotonic_sqlite_offset(db_session, admin):
    event_one = create_file_event(
        db_session,
        event_type="file.created",
        actor_user_id=admin.id,
        request_id="req-1",
        payload={"name": "a.txt"},
    )
    event_two = create_file_event(
        db_session,
        event_type="file.deleted",
        actor_user_id=admin.id,
        request_id="req-2",
        payload={"name": "b.txt"},
    )
    db_session.commit()

    assert event_one.offset == 1
    assert event_two.offset == 2


def test_trim_file_events_older_than_deletes_only_events_before_cutoff(db_session):
    now = dt.datetime.now(dt.UTC)
    old_event = FileEventFactory.build(
        offset=1,
        request_id="req-old",
        created_at=now - dt.timedelta(days=31),
    )
    cutoff_event = FileEventFactory.build(
        offset=2,
        request_id="req-cutoff",
        created_at=now - dt.timedelta(days=30),
    )
    recent_event = FileEventFactory.build(
        offset=3,
        request_id="req-recent",
        created_at=now - dt.timedelta(days=1),
    )
    db_session.add_all([old_event, cutoff_event, recent_event])
    db_session.commit()

    deleted = trim_file_events_older_than(db_session, retention_days=30, now=now)

    remaining_request_ids = {
        event.request_id for event in db_session.scalars(select(FileEvent)).all()
    }
    assert deleted == 1
    assert remaining_request_ids == {"req-cutoff", "req-recent"}


def test_trim_file_events_respects_slowest_enabled_processor_cursor(db_session):
    now = dt.datetime.now(dt.UTC)
    db_session.add(
        Processor(
            name="meta_extract",
            kind="meta_extract",
            enabled=True,
            source="seed",
            subscribed_event_types=["file.created"],
            config={},
            last_committed_offset=1,
        )
    )
    db_session.add_all(
        [
            FileEventFactory.build(
                offset=1,
                request_id="safe-old",
                created_at=now - dt.timedelta(days=31),
            ),
            FileEventFactory.build(
                offset=2,
                request_id="unsafe-old",
                created_at=now - dt.timedelta(days=31),
            ),
        ]
    )
    db_session.commit()

    deleted = trim_file_events_older_than(db_session, retention_days=30, now=now)

    remaining_request_ids = {
        event.request_id for event in db_session.scalars(select(FileEvent)).all()
    }
    assert deleted == 1
    assert remaining_request_ids == {"unsafe-old"}
