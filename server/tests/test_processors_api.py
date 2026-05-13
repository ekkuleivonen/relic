"""Admin API tests for /api/processors."""

import uuid

import pytest
from api.app import app
from database import get_db
from enums import UserRole
from fastapi.testclient import TestClient
from models import AuditEvent, Base, Processor
from processors.registry import init_builtin_substrates
from services.auth import create_session_token
from services.file_events import create_file_event
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import FolderFactory, ProcessorFactory, UserFactory


@pytest.fixture(autouse=True)
def _register_substrates() -> None:
    init_builtin_substrates()


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


def _create_event(db_session, *, event_type="file.created"):
    return create_file_event(
        db_session,
        event_type=event_type,
        file_id=uuid.uuid4(),
        payload={},
    )


def test_list_substrates_includes_meta_extract(client):
    response = client.get("/api/processors/substrates")
    assert response.status_code == 200
    body = response.json()
    assert any(item["kind"] == "meta_extract" for item in body["items"])


def test_create_processor_returns_lag(client, db_session):
    response = client.post(
        "/api/processors/",
        json={"name": "meta_extract", "kind": "meta_extract"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "meta_extract"
    assert body["kind"] == "meta_extract"
    assert body["enabled"] is True
    assert body["pending_count"] == 0
    assert body["head_offset"] == 0
    assert sorted(body["subscribed_event_types"]) == sorted(
        ["file.created", "file.updated", "file.copied", "file.renamed"]
    )
    assert body["folder_scopes"] == []


def test_create_processor_accepts_folder_scopes(client, db_session):
    folder = FolderFactory.build()
    db_session.add(folder)
    db_session.commit()

    response = client.post(
        "/api/processors/",
        json={
            "name": "meta_extract",
            "kind": "meta_extract",
            "folder_scopes": [{"folder_id": str(folder.id), "cascade": True}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["folder_scopes"] == [{"folder_id": str(folder.id), "cascade": True}]


def test_list_processors_reports_pending(client, db_session):
    processor = ProcessorFactory.build(
        name="meta_extract", subscribed_event_types=["file.created"]
    )
    db_session.add(processor)
    db_session.flush()
    _create_event(db_session)
    db_session.commit()

    response = client.get("/api/processors/")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["pending_count"] == 1
    assert body["items"][0]["head_offset"] == 1


def test_update_processor_disables_via_patch(client, db_session):
    processor = ProcessorFactory.build(name="meta_extract")
    db_session.add(processor)
    db_session.commit()

    response = client.patch(f"/api/processors/{processor.id}", json={"enabled": False})

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    db_session.expire_all()
    assert db_session.get(Processor, processor.id).enabled is False


def test_rewind_cursor_via_route(client, db_session):
    processor = ProcessorFactory.build(name="meta_extract", last_committed_offset=10)
    db_session.add(processor)
    db_session.commit()

    response = client.post(
        f"/api/processors/{processor.id}/rewind",
        json={"target_offset": 0, "reason": "replay"},
    )

    assert response.status_code == 200
    assert response.json()["last_committed_offset"] == 0


def test_skip_stuck_event_via_route(client, db_session):
    processor = ProcessorFactory.build(
        name="meta_extract",
        subscribed_event_types=["file.created"],
        last_committed_offset=0,
    )
    db_session.add(processor)
    db_session.flush()
    event = _create_event(db_session)
    db_session.commit()

    response = client.post(
        f"/api/processors/{processor.id}/skip",
        json={"event_id": str(event.id), "reason": "poison"},
    )

    assert response.status_code == 200
    assert response.json()["last_committed_offset"] == event.offset
    audit = db_session.scalars(
        select(AuditEvent).where(AuditEvent.operation == "processor.cursor.skipped")
    ).one()
    assert audit.actor_id is not None


def test_delete_processor_blocked_for_seeded(client, db_session):
    processor = ProcessorFactory.build(name="meta_extract", source="seed")
    db_session.add(processor)
    db_session.commit()

    response = client.delete(f"/api/processors/{processor.id}")
    assert response.status_code == 400


def test_delete_processor_succeeds_for_admin_managed(client, db_session):
    processor = ProcessorFactory.build(name="webhook:acme", source="admin")
    db_session.add(processor)
    db_session.commit()

    response = client.delete(f"/api/processors/{processor.id}")
    assert response.status_code == 204
    assert (
        db_session.scalars(
            select(Processor).where(Processor.id == processor.id)
        ).first()
        is None
    )


def test_processors_routes_require_admin(db_session):
    user = UserFactory.build(role=UserRole.USER)
    db_session.add(user)
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(user))
            response = test_client.get("/api/processors/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_create_processor_rejects_invalid_kind(client):
    response = client.post(
        "/api/processors/",
        json={"name": "x", "kind": "no_such_kind"},
    )
    assert response.status_code == 400


def test_create_processor_validates_event_types(client):
    response = client.post(
        "/api/processors/",
        json={
            "name": "x",
            "kind": "meta_extract",
            "subscribed_event_types": ["file.bogus"],
        },
    )
    assert response.status_code == 400
