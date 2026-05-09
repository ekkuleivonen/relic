import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from models import Base, User
from schema_plan import UserRole
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
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def add_user(db_session, *, role: UserRole = UserRole.ADMIN) -> User:
    user = User(
        name="Ada Lovelace",
        email="ada@example.com",
        password_hash=hash_password("password123"),
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_login_sets_session_cookie_and_returns_user(client, db_session):
    add_user(db_session)

    response = client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "ada@example.com"
    assert "relic_session" in response.cookies


def test_session_requires_valid_cookie(client):
    response = client.get("/auth/session")

    assert response.status_code == 401


def test_admin_api_rejects_non_admin_session(client, db_session):
    add_user(db_session, role=UserRole.USER)
    assert (
        client.post(
            "/auth/login",
            json={"email": "ada@example.com", "password": "password123"},
        ).status_code
        == 200
    )

    response = client.get("/users/")

    assert response.status_code == 403


def test_logout_clears_session(client, db_session):
    add_user(db_session)
    assert (
        client.post(
            "/auth/login",
            json={"email": "ada@example.com", "password": "password123"},
        ).status_code
        == 200
    )

    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert client.get("/auth/session").status_code == 401
