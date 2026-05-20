import pytest
from api.app import app
from enums import Permission, UserRole
from fastapi.testclient import TestClient
from infra.db.engine import get_db
from infra.db.models import AccessKey, File, Folder, FolderAccess
from tests.factories.models import (
    AccessKeyFactory,
    BlobFactory,
    StorageBackendFactory,
    UserFactory,
)


def bearer_headers(access_key: AccessKey) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_key.key_id}:{access_key.secret_access_key}",
    }


@pytest.fixture()
def user(db_session):
    user = UserFactory.build(name="Service User", email="service@relic.local")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def access_key(db_session, user):
    access_key = AccessKeyFactory.build(actor_id=user.id, name="integration")
    db_session.add(access_key)
    db_session.commit()
    return access_key


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def root_folder(db_session):
    root = Folder(name="", parent_id=None)
    db_session.add(root)
    db_session.commit()
    return root


def add_folder(db_session, parent: Folder, name: str) -> Folder:
    folder = Folder(name=name, parent_id=parent.id)
    db_session.add(folder)
    db_session.commit()
    return folder


def grant_access(db_session, user, folder, permissions: int) -> None:
    db_session.add(
        FolderAccess(
            actor_id=user.id,
            folder_id=folder.id,
            permissions=permissions,
        )
    )
    db_session.commit()


def test_bearer_access_key_can_fetch_folder_tree(
    client, db_session, user, access_key, root_folder
):
    loans = add_folder(db_session, root_folder, "loans")
    grant_access(db_session, user, loans, int(Permission.READ))

    response = client.get("/api/folders/tree", headers=bearer_headers(access_key))

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == ""
    assert len(body["children"]) == 1
    assert body["children"][0]["name"] == "loans"
    assert body["children"][0]["effective_permissions"] == int(Permission.READ)


def test_bearer_access_key_can_patch_file_meta(
    client, db_session, user, access_key, root_folder
):
    bucket = StorageBackendFactory.build()
    db_session.add(bucket)
    db_session.commit()

    loans = add_folder(db_session, root_folder, "loans")
    grant_access(
        db_session,
        user,
        loans,
        int(Permission.READ | Permission.ENRICH),
    )

    blob = BlobFactory.build(storage_backend_id=bucket.id)
    db_session.add(blob)
    db_session.commit()

    file = File(
        folder_id=loans.id,
        blob_id=blob.id,
        actor_id=user.id,
        name="statement.pdf",
        meta={"tags": ["old"]},
    )
    db_session.add(file)
    db_session.commit()

    response = client.patch(
        f"/api/files/{file.id}/meta",
        headers=bearer_headers(access_key),
        json={"meta": {"tags": ["new"], "source": "integration"}},
    )

    assert response.status_code == 200
    assert response.json()["meta"] == {"tags": ["new"], "source": "integration"}


def test_invalid_bearer_token_returns_401_and_audits(client, db_session):
    response = client.get(
        "/api/folders/tree",
        headers={"Authorization": "Bearer RKINVALID:wrong-secret"},
    )

    assert response.status_code == 401

    from infra.db.models import AuditEvent
    from sqlalchemy import select

    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.operation == "auth.bearer.failed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.status == "failed"
    assert event.meta["reason"] == "unknown_key"
    assert event.meta["key_id"] == "RKINVALID"


def test_revoked_access_key_returns_401_and_audits(
    client, db_session, access_key, root_folder
):
    access_key.revoked_at = access_key.created_at
    db_session.commit()

    response = client.get("/api/folders/tree", headers=bearer_headers(access_key))

    assert response.status_code == 401

    from infra.db.models import AuditEvent
    from sqlalchemy import select

    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.operation == "auth.bearer.failed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.meta["reason"] == "revoked"
    assert event.meta["key_id"] == access_key.key_id


def test_malformed_bearer_token_returns_401_and_audits(client, db_session):
    response = client.get(
        "/api/folders/tree",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401

    from infra.db.models import AuditEvent
    from sqlalchemy import select

    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.operation == "auth.bearer.failed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.meta["reason"] == "malformed"
    assert "key_id" not in event.meta


def test_bearer_access_key_respects_folder_permissions(
    client, db_session, user, access_key, root_folder
):
    secret = add_folder(db_session, root_folder, "secret")
    add_folder(db_session, root_folder, "public")
    grant_access(db_session, user, secret, int(Permission.READ))

    response = client.get("/api/folders/tree", headers=bearer_headers(access_key))

    assert response.status_code == 200
    visible_names = {child["name"] for child in response.json()["children"]}
    assert visible_names == {"secret"}


def test_admin_access_key_can_reach_admin_routes(client, db_session):
    admin = UserFactory.build(
        name="Admin",
        email="admin@relic.local",
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    db_session.commit()
    access_key = AccessKeyFactory.build(actor_id=admin.id, name="automation")
    db_session.add(access_key)
    db_session.commit()

    response = client.get("/api/users/", headers=bearer_headers(access_key))

    assert response.status_code == 200


def test_user_access_key_cannot_reach_admin_routes(client, access_key):
    response = client.get("/api/users/", headers=bearer_headers(access_key))

    assert response.status_code == 403
