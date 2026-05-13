import pytest
from api.app import app
from database import get_db
from enums import UserRole
from fastapi.testclient import TestClient
from models import AuditEvent, Base, User
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
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
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "ada@example.com"
    assert "relic_session" in response.cookies
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.operation == "auth.login.succeeded")
    )
    assert event is not None
    assert event.actor_user_id is not None
    assert event.meta == {"email": "ada@example.com"}


def test_failed_login_writes_audit_event(client, db_session):
    add_user(db_session)

    response = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "wrong"},
    )

    assert response.status_code == 400
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.operation == "auth.login.failed")
    )
    assert event is not None
    assert event.status == "failed"
    assert event.actor_user_id is None
    assert event.meta == {"email": "ada@example.com"}


def test_session_requires_valid_cookie(client):
    response = client.get("/api/auth/session")

    assert response.status_code == 401


def test_admin_api_rejects_non_admin_session(client, db_session):
    add_user(db_session, role=UserRole.USER)
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "ada@example.com", "password": "password123"},
        ).status_code
        == 200
    )

    response = client.get("/api/users/")

    assert response.status_code == 403


def test_logout_clears_session(client, db_session):
    add_user(db_session)
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "ada@example.com", "password": "password123"},
        ).status_code
        == 200
    )

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert client.get("/api/auth/session").status_code == 401
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.operation == "auth.logout")
    )
    assert event is not None
    assert event.actor_user_id is not None
