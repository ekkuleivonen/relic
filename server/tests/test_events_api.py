import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from models import Base, Event
from schema_plan import UserRole
from services.auth import create_session_token
from tests.factories.models import EventFactory, UserFactory


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


def test_list_events_returns_recent_events_first(client, db_session, admin):
    now = dt.datetime.now(dt.UTC)
    older = EventFactory.build(
        source="s3_gateway",
        operation="GET",
        actor_user_id=admin.id,
        request_id="req-old",
        file_ids=["file-1"],
        meta={"bucket": "photos", "key": "old.jpg"},
        created_at=now - dt.timedelta(minutes=1),
        updated_at=now - dt.timedelta(minutes=1),
    )
    newer = EventFactory.build(
        source="relic_api",
        operation="folder.move",
        actor_user_id=admin.id,
        request_id="req-new",
        folder_ids=["folder-1"],
        meta={"destination_folder_id": "folder-2"},
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([older, newer])
    db_session.commit()

    response = client.get("/api/events/")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [item["request_id"] for item in body["items"]] == ["req-new", "req-old"]
    assert body["items"][0]["actor"]["email"] == "admin@relic.local"
    assert body["items"][0]["metadata"] == {"destination_folder_id": "folder-2"}


def test_list_events_filters_and_paginates(client, db_session, admin):
    db_session.add_all(
        [
            EventFactory.build(
                source="s3_gateway",
                operation="GET",
                actor_user_id=admin.id,
                request_id="req-get-1",
            ),
            EventFactory.build(
                source="s3_gateway",
                operation="PUT",
                actor_user_id=admin.id,
                request_id="req-put-1",
            ),
            EventFactory.build(
                source="relic_api",
                operation="GET",
                actor_user_id=admin.id,
                request_id="req-api-1",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/events/",
        params={"source": "s3_gateway", "operation": "GET", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["request_id"] == "req-get-1"


def test_list_events_rejects_invalid_status(client):
    response = client.get("/api/events/", params={"status": "maybe"})

    assert response.status_code == 400
    assert response.json()["detail"] == "status must be one of ['failed', 'succeeded']"


def test_clear_events_removes_all_events(client, db_session, admin):
    db_session.add_all(
        [
            EventFactory.build(actor_user_id=admin.id, request_id="req-1"),
            EventFactory.build(actor_user_id=admin.id, request_id="req-2"),
        ]
    )
    db_session.commit()

    response = client.delete("/api/events/")

    assert response.status_code == 204
    assert db_session.scalars(select(Event)).all() == []


def test_clear_events_requires_admin(db_session):
    user = UserFactory.build(role=UserRole.USER)
    db_session.add(user)
    db_session.add(EventFactory.build(request_id="req-1"))
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(user))
            response = test_client.delete("/api/events/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert len(db_session.scalars(select(Event)).all()) == 1
