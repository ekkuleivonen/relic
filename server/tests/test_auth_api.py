import pytest
from enums import UserRole
from infra.db.models import User
from sqlalchemy import select
from utils.passwords import hash_password




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


def test_failed_login_returns_bad_request(client, db_session):
    add_user(db_session)

    response = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "wrong"},
    )

    assert response.status_code == 400


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
