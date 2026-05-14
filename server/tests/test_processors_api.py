"""Admin API tests for /api/processors."""

import uuid

import pytest
from api.app import app
from database import get_db
from enums import UserRole
from fastapi.testclient import TestClient
from models import AuditEvent, Base, Processor
from processors.registry import init_builtin_processors
from services.auth import create_session_token
from services.file_events import create_file_event
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import FolderFactory, ProcessorFactory, UserFactory


@pytest.fixture(autouse=True)
def _register_processors() -> None:
    init_builtin_processors()


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


def test_list_processor_kinds_returns_seed_kinds(client):
    response = client.get("/api/processors/kinds")
    assert response.status_code == 200
    body = response.json()
    file_info = next(item for item in body["items"] if item["kind"] == "file_info")
    assert file_info["display_name"] == "File info"
    assert file_info["default_task_queue"] == "relic:tasks:file_info"

    image_meta = next(item for item in body["items"] if item["kind"] == "image_meta")
    assert "image/" in image_meta["valid_mimetype_prefixes"]
    assert "processor.file_info.completed" in image_meta["valid_event_types"]

    webhook = next(
        item for item in body["items"] if item["kind"] == "webhook_event_dispatch"
    )
    assert webhook["display_name"] == "Webhook event dispatch"
    assert webhook["default_task_queue"] == "relic:tasks:webhook_event_dispatch"
    # Webhook valid event types are derived dynamically from registered kinds.
    assert "processor.image_meta.completed" in webhook["valid_event_types"]
    assert "processor.file_info.completed" in webhook["valid_event_types"]
    assert {
        "value": "file.created",
        "label": "file.created",
        "default": True,
    } in webhook["event_type_options"]
    assert webhook["config_schema"]["properties"]["url"]["format"] == "uri"
    assert webhook["config_schema"]["properties"]["secret"]["writeOnly"] is True


def test_list_processor_folder_options_returns_flat_paths(client, db_session):
    root = FolderFactory.build(name="")
    db_session.add(root)
    db_session.flush()
    child = FolderFactory.build(name="inbox", parent_id=root.id)
    db_session.add(child)
    db_session.commit()

    response = client.get("/api/processors/folder-options")

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"id": str(root.id), "name": "", "path": "/"},
        {"id": str(child.id), "name": "inbox", "path": "/inbox"},
    ]


def test_create_processor_returns_lag(client, db_session):
    response = client.post(
        "/api/processors/",
        json={"name": "file_info", "kind": "file_info"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "file_info"
    assert body["kind"] == "file_info"
    assert body["enabled"] is True
    assert body["pending_count"] == 0
    assert body["head_offset"] == 0
    assert sorted(body["subscribed_event_types"]) == sorted(
        ["file.created", "file.updated", "file.copied", "file.renamed"]
    )
    assert body["folder_scopes"] == []
    assert body["mimetype_prefixes"] == []
    assert body["extensions"] == []


def test_create_webhook_processor_redacts_secret(client):
    response = client.post(
        "/api/processors/",
        json={
            "name": "webhook:acme",
            "kind": "webhook_event_dispatch",
            "config": {
                "url": "https://example.com/relic",
                "secret": "a" * 32,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["config"]["url"] == "https://example.com/relic"
    assert body["config"]["secret"] == "********"


def test_create_processor_accepts_folder_scopes(client, db_session):
    folder = FolderFactory.build()
    db_session.add(folder)
    db_session.commit()

    response = client.post(
        "/api/processors/",
        json={
            "name": "file_info",
            "kind": "file_info",
            "folder_scopes": [{"folder_id": str(folder.id), "cascade": True}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["folder_scopes"] == [{"folder_id": str(folder.id), "cascade": True}]


def test_create_image_meta_processor_with_mimetype_filter(client):
    response = client.post(
        "/api/processors/",
        json={
            "name": "image_meta",
            "kind": "image_meta",
            "mimetype_prefixes": ["image/"],
            "extensions": ["png", "jpg"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mimetype_prefixes"] == ["image/"]
    assert body["extensions"] == ["png", "jpg"]


def test_list_processors_reports_pending(client, db_session):
    processor = ProcessorFactory.build(
        name="file_info", subscribed_event_types=["file.created"]
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
    processor = ProcessorFactory.build(name="file_info")
    db_session.add(processor)
    db_session.commit()

    response = client.patch(f"/api/processors/{processor.id}", json={"enabled": False})

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    db_session.expire_all()
    assert db_session.get(Processor, processor.id).enabled is False


def test_update_processor_rejects_folder_scopes_field(client, db_session):
    processor = ProcessorFactory.build(name="file_info")
    db_session.add(processor)
    db_session.commit()

    response = client.patch(
        f"/api/processors/{processor.id}",
        json={"folder_scopes": [{"folder_id": str(uuid.uuid4()), "cascade": True}]},
    )
    assert response.status_code == 422


def test_rewind_cursor_via_route(client, db_session):
    processor = ProcessorFactory.build(name="file_info", last_committed_offset=10)
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
        name="file_info",
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
    processor = ProcessorFactory.build(name="file_info", source="seed")
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
            "kind": "file_info",
            "subscribed_event_types": ["file.bogus"],
        },
    )
    assert response.status_code == 400
