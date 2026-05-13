import datetime as dt
import uuid

import pytest
from api.app import app
from database import get_db
from enums import UserRole
from fastapi.testclient import TestClient
from models import Base, MaintenanceEvent
from services.auth import create_session_token
from services.maintenance_events import (
    create_maintenance_event,
    trim_maintenance_events_older_than,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import MaintenanceEventFactory, UserFactory


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


def test_list_maintenance_events_returns_recent_events_first(client, db_session):
    batch_id = uuid.uuid4()
    older = MaintenanceEventFactory.build(
        job="bucket_probe",
        action="bucket.probe_ok",
        batch_id=batch_id,
        meta={"put_ms": 1},
        created_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
    )
    newer = MaintenanceEventFactory.build(
        job="purge_dereferenced_blobs",
        action="blob.purged",
        batch_id=batch_id,
        blob_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        meta={"freed_bytes": 100},
        created_at=dt.datetime.now(dt.UTC),
    )
    db_session.add_all([older, newer])
    db_session.commit()

    response = client.get("/api/maintenance-events/")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [item["action"] for item in body["items"]] == [
        "blob.purged",
        "bucket.probe_ok",
    ]
    assert body["items"][0]["metadata"] == {"freed_bytes": 100}


def test_list_maintenance_events_filters_and_paginates(client, db_session):
    db_session.add_all(
        [
            MaintenanceEventFactory.build(
                job="bucket_probe",
                action="bucket.probe_ok",
                status="succeeded",
            ),
            MaintenanceEventFactory.build(
                job="bucket_probe",
                action="bucket.probe_failed",
                status="failed",
            ),
            MaintenanceEventFactory.build(
                job="purge_dereferenced_blobs",
                action="blob.purged",
                status="succeeded",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/maintenance-events/",
        params={"job": "bucket_probe", "status": "failed", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "bucket.probe_failed"


def test_list_maintenance_events_rejects_invalid_status(client):
    response = client.get("/api/maintenance-events/", params={"status": "maybe"})

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "status must be one of ['failed', 'skipped', 'succeeded']"
    )


def test_clear_maintenance_events_requires_admin(db_session):
    user = UserFactory.build(role=UserRole.USER)
    db_session.add(user)
    db_session.add(MaintenanceEventFactory.build())
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(user))
            response = test_client.delete("/api/maintenance-events/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert len(db_session.scalars(select(MaintenanceEvent)).all()) == 1


def test_create_maintenance_event_writes_event(db_session):
    batch_id = uuid.uuid4()
    blob_id = uuid.uuid4()

    event = create_maintenance_event(
        db_session,
        job="purge_dereferenced_blobs",
        action="blob.purged",
        status="succeeded",
        batch_id=batch_id,
        blob_id=blob_id,
        duration_ms=12,
        metadata={"freed_bytes": 100},
    )
    db_session.commit()

    assert event.id is not None
    assert event.batch_id == batch_id
    assert event.blob_id == blob_id
    assert event.meta == {"freed_bytes": 100}


def test_trim_maintenance_events_older_than_deletes_only_events_before_cutoff(
    db_session,
):
    now = dt.datetime.now(dt.UTC)
    old_event = MaintenanceEventFactory.build(
        created_at=now - dt.timedelta(days=31),
        meta={"name": "old"},
    )
    cutoff_event = MaintenanceEventFactory.build(
        created_at=now - dt.timedelta(days=30),
        meta={"name": "cutoff"},
    )
    recent_event = MaintenanceEventFactory.build(
        created_at=now - dt.timedelta(days=1),
        meta={"name": "recent"},
    )
    db_session.add_all([old_event, cutoff_event, recent_event])
    db_session.commit()

    deleted = trim_maintenance_events_older_than(db_session, retention_days=30, now=now)

    remaining_names = {
        event.meta["name"]
        for event in db_session.scalars(select(MaintenanceEvent)).all()
    }
    assert deleted == 1
    assert remaining_names == {"cutoff", "recent"}
