import pytest
from api.app import app
from infra.db.engine import get_db
from enums import UserRole
from fastapi.testclient import TestClient
from infra.db.models import AccessKey, Base
from infra.db.stores.auth import create_session_token
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import AccessKeyFactory, UserFactory



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


def test_create_access_key_returns_secret_once(client, db_session):
    alice = UserFactory.build(name="Alice", email="alice@relic.local")
    db_session.add(alice)
    db_session.commit()

    response = client.post(
        "/api/access-keys/",
        json={"actor_id": str(alice.id), "name": "duckdb ingest"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "duckdb ingest"
    assert body["key_id"].startswith("RK")
    assert len(body["secret_access_key"]) > 20
    assert body["user"]["name"] == "Alice"
    assert body["user"]["email"] == "alice@relic.local"

    access_key = db_session.scalar(
        select(AccessKey).where(AccessKey.key_id == body["key_id"])
    )
    assert access_key is not None
    assert access_key._secret_access_key != body["secret_access_key"]
    assert access_key.secret_access_key == body["secret_access_key"]

    list_response = client.get("/api/access-keys/")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    assert listed[0]["key_id"] == body["key_id"]
    assert "secret_access_key" not in listed[0]


def test_list_access_keys_embeds_users(client, db_session):
    alice = UserFactory.build(name="Alice", email="alice@relic.local")
    bob = UserFactory.build(name="Bob", email="bob@relic.local")
    db_session.add_all([alice, bob])
    db_session.commit()
    db_session.add_all(
        [
            AccessKeyFactory.build(actor_id=bob.id, name="bob key"),
            AccessKeyFactory.build(actor_id=alice.id, name="alice key"),
        ]
    )
    db_session.commit()

    response = client.get("/api/access-keys/")

    assert response.status_code == 200
    body = response.json()
    assert [row["user"]["email"] for row in body] == [
        "alice@relic.local",
        "bob@relic.local",
    ]
    assert [row["name"] for row in body] == ["alice key", "bob key"]


def test_revoke_access_key_is_idempotent(client, db_session):
    alice = UserFactory.build(name="Alice", email="alice@relic.local")
    db_session.add(alice)
    db_session.commit()
    access_key = AccessKeyFactory.build(actor_id=alice.id)
    db_session.add(access_key)
    db_session.commit()

    first_response = client.post(f"/api/access-keys/{access_key.key_id}/revoke")
    second_response = client.post(f"/api/access-keys/{access_key.key_id}/revoke")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["revoked_at"] is not None
    assert second_response.json()["revoked_at"] == first_response.json()["revoked_at"]


def test_access_key_user_must_exist(client):
    response = client.post(
        "/api/access-keys/",
        json={
            "actor_id": "00000000-0000-0000-0000-000000000000",
            "name": "missing",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
