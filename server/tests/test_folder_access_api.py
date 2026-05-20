import uuid

import pytest
from api.app import app
from infra.db.engine import get_db
from enums import Permission, UserRole
from fastapi.testclient import TestClient
from infra.db.models import Base, FolderAccess
from infra.db.stores.auth import create_session_token
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import FolderFactory, UserFactory



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


@pytest.fixture()
def root_folder(db_session):
    root = FolderFactory.build(name="", parent_id=None)
    db_session.add(root)
    db_session.commit()
    return root


def add_folder(db_session, parent, name):
    folder = FolderFactory.build(name=name, parent_id=parent.id)
    db_session.add(folder)
    db_session.commit()
    return folder


def test_list_returns_empty_when_no_grants(client):
    response = client.get("/api/folder-access/")

    assert response.status_code == 200
    assert response.json() == []


def test_grant_and_list_resolves_folder_paths(client, db_session, root_folder):
    loans = add_folder(db_session, root_folder, "loans")
    applications = add_folder(db_session, loans, "applications")
    alice = UserFactory.build(name="Alice", email="alice@relic.local")
    db_session.add(alice)
    db_session.commit()

    grant = client.post(
        "/api/folder-access/",
        json={
            "actor_id": str(alice.id),
            "folder_id": str(applications.id),
            "permissions": int(Permission.READ | Permission.WRITE),
        },
    )

    assert grant.status_code == 200
    body = grant.json()
    assert body["folder_path"] == "/loans/applications"
    assert body["permissions"] == int(Permission.READ | Permission.WRITE)
    assert body["user"]["email"] == "alice@relic.local"

    listing = client.get("/api/folder-access/").json()
    assert len(listing) == 1
    assert listing[0]["folder_path"] == "/loans/applications"


def test_grant_on_root_renders_path_as_slash(client, db_session, root_folder):
    bob = UserFactory.build(email="bob@relic.local")
    db_session.add(bob)
    db_session.commit()

    response = client.post(
        "/api/folder-access/",
        json={
            "actor_id": str(bob.id),
            "folder_id": str(root_folder.id),
            "permissions": int(Permission.READ),
        },
    )

    assert response.status_code == 200
    assert response.json()["folder_path"] == "/"


def test_grant_is_idempotent_on_user_folder_pair(client, db_session, root_folder):
    alice = UserFactory.build(email="alice@relic.local")
    db_session.add(alice)
    db_session.commit()
    payload = {
        "actor_id": str(alice.id),
        "folder_id": str(root_folder.id),
        "permissions": int(Permission.READ),
    }

    first = client.post("/api/folder-access/", json=payload).json()
    payload["permissions"] = int(Permission.READ | Permission.WRITE)
    second = client.post("/api/folder-access/", json=payload).json()

    assert first["id"] == second["id"]
    assert second["permissions"] == int(Permission.READ | Permission.WRITE)
    rows = db_session.scalars(select(FolderAccess)).all()
    assert len(rows) == 1


def test_grant_rejects_unknown_permission_bits(client, db_session, root_folder):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/folder-access/",
        json={
            "actor_id": str(user.id),
            "folder_id": str(root_folder.id),
            "permissions": 64,
        },
    )

    assert response.status_code == 400
    assert "unknown bits" in response.json()["detail"]


def test_grant_rejects_write_without_read(client, db_session, root_folder):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/folder-access/",
        json={
            "actor_id": str(user.id),
            "folder_id": str(root_folder.id),
            "permissions": int(Permission.WRITE),
        },
    )

    assert response.status_code == 400
    assert "read" in response.json()["detail"].lower()


def test_grant_rejects_removed_admin_permission_bit(client, db_session, root_folder):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/folder-access/",
        json={
            "actor_id": str(user.id),
            "folder_id": str(root_folder.id),
            "permissions": 16,
        },
    )

    assert response.status_code == 400
    assert "unknown bits" in response.json()["detail"]


def test_grant_404_when_user_missing(client, db_session, root_folder):
    response = client.post(
        "/api/folder-access/",
        json={
            "actor_id": str(uuid.uuid4()),
            "folder_id": str(root_folder.id),
            "permissions": int(Permission.READ),
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_grant_404_when_folder_missing(client, db_session):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/folder-access/",
        json={
            "actor_id": str(user.id),
            "folder_id": str(uuid.uuid4()),
            "permissions": int(Permission.READ),
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Folder not found"


def test_revoke_removes_row(client, db_session, root_folder):
    alice = UserFactory.build(email="alice@relic.local")
    db_session.add(alice)
    db_session.commit()
    grant = client.post(
        "/api/folder-access/",
        json={
            "actor_id": str(alice.id),
            "folder_id": str(root_folder.id),
            "permissions": int(Permission.READ),
        },
    ).json()

    response = client.delete(f"/api/folder-access/{grant['id']}")

    assert response.status_code == 204
    assert db_session.scalars(select(FolderAccess)).all() == []


def test_revoke_404_when_missing(client):
    response = client.delete(f"/api/folder-access/{uuid.uuid4()}")

    assert response.status_code == 404


def test_non_admin_is_forbidden(db_session, root_folder):
    def override_get_db():
        yield db_session

    user = UserFactory.build(email="user@relic.local", role=UserRole.USER)
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as anon_client:
            anon_client.cookies.set("relic_session", create_session_token(user))
            response = anon_client.get("/api/folder-access/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
