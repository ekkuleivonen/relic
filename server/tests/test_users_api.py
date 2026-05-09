import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from models import Base, User
from schema_plan import UserRole
from services.auth import create_session_token
from utils.passwords import hash_password


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
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    admin = User(
        name="Admin",
        email="admin@relic.local",
        password_hash=hash_password("password"),
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    db_session.commit()
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(admin))
            yield test_client
    finally:
        app.dependency_overrides.clear()


def user_payload(email: str = "ada@example.com") -> dict:
    return {
        "name": "Ada Lovelace",
        "email": email,
        "password": "correct horse battery staple",
        "role": UserRole.ADMIN,
    }


def test_create_and_list_users(client, db_session):
    create_response = client.post("/api/users/", json=user_payload())

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "Ada Lovelace"
    assert created["email"] == "ada@example.com"
    assert created["role"] == UserRole.ADMIN
    assert "password_hash" not in created
    assert "password" not in created

    user = db_session.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    assert user.password_hash.startswith("pbkdf2_sha256$")
    assert user.password_hash != "correct horse battery staple"

    list_response = client.get("/api/users/")

    assert list_response.status_code == 200
    assert [user["email"] for user in list_response.json()] == [
        "ada@example.com",
        "admin@relic.local",
    ]


def test_list_users_allows_local_development_email(client):
    response = client.get("/api/users/")

    assert response.status_code == 200
    assert "admin@relic.local" in [user["email"] for user in response.json()]


def test_create_user_rejects_duplicate_email(client):
    assert client.post("/api/users/", json=user_payload()).status_code == 200

    response = client.post("/api/users/", json=user_payload())

    assert response.status_code == 409
    assert response.json()["detail"] == "User email already exists"


def test_update_user_mutable_fields(client, db_session):
    user = User(
        name="Ada Lovelace",
        email="ada@example.com",
        password_hash=hash_password("old-password"),
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    db_session.commit()

    response = client.patch(
        f"/api/users/{user.id}",
        json={
            "name": "Grace Hopper",
            "email": "grace@example.com",
            "password": "new-password",
            "role": UserRole.USER,
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Grace Hopper"
    assert updated["email"] == "grace@example.com"
    assert updated["role"] == UserRole.USER

    db_session.refresh(user)
    assert user.password_hash != hash_password("old-password")


def test_delete_user(client, db_session):
    user = User(
        name="Ada Lovelace",
        email="ada@example.com",
        password_hash=hash_password("password"),
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    db_session.commit()

    response = client.delete(f"/api/users/{user.id}")

    assert response.status_code == 204
    assert db_session.get(User, user.id) is None
