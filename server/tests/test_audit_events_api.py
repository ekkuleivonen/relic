import datetime as dt

import pytest
from api.app import app
from database import get_db
from enums import UserRole
from fastapi.testclient import TestClient
from models import AuditEvent, Base
from services.audit_events import trim_audit_events_older_than
from services.auth import create_session_token
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import AuditEventFactory, UserFactory


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


def test_list_audit_events_returns_recent_audit_events_first(client, db_session, admin):
    now = dt.datetime.now(dt.UTC)
    older = AuditEventFactory.build(
        operation="GET",
        actor_id=admin.id,
        request_id="req-old",
        meta={"bucket": "photos", "key": "old.jpg", "file_id": "file-1"},
        created_at=now - dt.timedelta(minutes=1),
        updated_at=now - dt.timedelta(minutes=1),
    )
    newer = AuditEventFactory.build(
        operation="folder.move",
        actor_id=admin.id,
        request_id="req-new",
        meta={"destination_folder_id": "folder-2", "folder_id": "folder-1"},
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([older, newer])
    db_session.commit()

    response = client.get("/api/audit-events/")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [item["request_id"] for item in body["items"]] == ["req-new", "req-old"]
    assert body["items"][0]["actor"]["email"] == "admin@relic.local"
    assert body["items"][0]["metadata"] == {
        "destination_folder_id": "folder-2",
        "folder_id": "folder-1",
    }
    assert "source" not in body["items"][0]


def test_list_audit_events_filters_and_paginates(client, db_session, admin):
    db_session.add_all(
        [
            AuditEventFactory.build(
                operation="GET",
                actor_id=admin.id,
                request_id="req-get-1",
            ),
            AuditEventFactory.build(
                operation="PUT",
                actor_id=admin.id,
                request_id="req-put-1",
            ),
            AuditEventFactory.build(
                operation="GET",
                actor_id=admin.id,
                request_id="req-api-1",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/audit-events/",
        params={"operation": "GET", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["operation"] == "GET"


def test_list_audit_events_rejects_invalid_status(client):
    response = client.get("/api/audit-events/", params={"status": "maybe"})

    assert response.status_code == 400
    assert response.json()["detail"] == "status must be one of ['failed', 'succeeded']"


def test_clear_audit_events_removes_all_audit_events(client, db_session, admin):
    db_session.add_all(
        [
            AuditEventFactory.build(actor_id=admin.id, request_id="req-1"),
            AuditEventFactory.build(actor_id=admin.id, request_id="req-2"),
        ]
    )
    db_session.commit()

    response = client.delete("/api/audit-events/")

    assert response.status_code == 204
    assert db_session.scalars(select(AuditEvent)).all() == []


def test_clear_audit_events_requires_admin(db_session):
    user = UserFactory.build(role=UserRole.USER)
    db_session.add(user)
    db_session.add(AuditEventFactory.build(request_id="req-1"))
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(user))
            response = test_client.delete("/api/audit-events/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert len(db_session.scalars(select(AuditEvent)).all()) == 1


def test_trim_audit_events_older_than_deletes_only_audit_events_before_cutoff(
    db_session,
):
    now = dt.datetime.now(dt.UTC)
    old_event = AuditEventFactory.build(
        request_id="req-old",
        created_at=now - dt.timedelta(days=31),
        updated_at=now - dt.timedelta(days=31),
    )
    cutoff_event = AuditEventFactory.build(
        request_id="req-cutoff",
        created_at=now - dt.timedelta(days=30),
        updated_at=now - dt.timedelta(days=30),
    )
    recent_event = AuditEventFactory.build(
        request_id="req-recent",
        created_at=now - dt.timedelta(days=1),
        updated_at=now - dt.timedelta(days=1),
    )
    db_session.add_all([old_event, cutoff_event, recent_event])
    db_session.commit()

    deleted = trim_audit_events_older_than(db_session, retention_days=30, now=now)

    remaining_request_ids = {
        event.request_id for event in db_session.scalars(select(AuditEvent)).all()
    }
    assert deleted == 1
    assert remaining_request_ids == {"req-cutoff", "req-recent"}
