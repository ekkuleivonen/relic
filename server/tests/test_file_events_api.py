import pytest
from api.app import app
from application.control_plane import file_event_emission
from application.uow_runner import run_with_uow
from enums import Permission, UserRole
from fastapi.testclient import TestClient
from infra.db.engine import get_db
from infra.db.models import File, Folder, FolderAccess
from infra.db.stores.auth import create_session_token
from tests.factories.models import (
    AccessKeyFactory,
    BlobFactory,
    StorageBackendFactory,
    UserFactory,
)


@pytest.fixture()
def user(db_session):
    user = UserFactory.build(name="Subscriber", email="sub@relic.local")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def client(db_session, user):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(user))
            yield test_client
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


def add_file(db_session, folder: Folder, user, name: str = "doc.pdf") -> File:
    bucket = StorageBackendFactory.build()
    db_session.add(bucket)
    db_session.flush()
    blob = BlobFactory.build(storage_backend_id=bucket.id)
    db_session.add(blob)
    db_session.flush()
    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        actor_id=user.id,
        name=name,
        meta={},
    )
    db_session.add(file)
    db_session.flush()
    return file


def seed_created_file(db_session, folder: Folder, user, name: str = "doc.pdf") -> File:
    file = add_file(db_session, folder, user, name=name)
    blob = file.blob_id
    from infra.db.models import Blob

    blob_row = db_session.get(Blob, blob)
    assert blob_row is not None
    run_with_uow(
        db_session,
        lambda uow: file_event_emission.emit_file_created(
            uow,
            file=file,
            blob=blob_row,
            origin="upload",
            actor_id=user.id,
        ),
    )
    db_session.commit()
    return file


def test_patch_meta_emits_file_meta_updated_event(
    client, db_session, user, root_folder
):
    inbox = add_folder(db_session, root_folder, "inbox")
    grant_access(
        db_session,
        user,
        inbox,
        int(Permission.READ | Permission.ENRICH),
    )
    file = add_file(db_session, inbox, user)
    db_session.commit()

    response = client.patch(
        f"/api/files/{file.id}/meta",
        json={"meta": {"status": "ready"}},
    )

    assert response.status_code == 200

    events = client.get("/api/file-events?types=file.meta_updated").json()
    assert events["has_more"] is False
    assert len(events["items"]) == 1
    body = events["items"][0]
    assert body["event_type"] == "file.meta_updated"
    assert body["file_id"] == str(file.id)
    assert body["folder_id"] == str(inbox.id)
    assert body["payload"]["meta"] == {"status": "ready"}


def test_delete_emits_file_deleted_event(client, db_session, user, root_folder):
    inbox = add_folder(db_session, root_folder, "inbox")
    grant_access(
        db_session,
        user,
        inbox,
        int(Permission.READ | Permission.DELETE),
    )
    file = add_file(db_session, inbox, user)
    db_session.commit()

    response = client.delete(f"/api/files/{file.id}")
    assert response.status_code == 204

    events = client.get("/api/file-events?types=file.deleted").json()
    assert len(events["items"]) == 1
    assert events["items"][0]["event_type"] == "file.deleted"
    assert events["items"][0]["payload"]["name"] == "doc.pdf"


def test_poll_after_cursor_returns_only_new_events(
    client, db_session, user, root_folder
):
    inbox = add_folder(db_session, root_folder, "inbox")
    grant_access(
        db_session,
        user,
        inbox,
        int(Permission.READ | Permission.ENRICH | Permission.DELETE),
    )
    first = seed_created_file(db_session, inbox, user, name="first.pdf")
    client.patch(f"/api/files/{first.id}/meta", json={"meta": {"n": 1}})

    initial = client.get("/api/file-events").json()
    assert len(initial["items"]) >= 1
    cursor = initial["cursor"]

    seed_created_file(db_session, inbox, user, name="second.pdf")

    page = client.get(f"/api/file-events?after={cursor}").json()
    assert all(item["seq"] > cursor for item in page["items"])
    assert any(item["event_type"] == "file.created" for item in page["items"])


def test_user_does_not_see_events_for_inaccessible_folder(
    client, db_session, user, root_folder
):
    secret = add_folder(db_session, root_folder, "secret")
    other = UserFactory.build(name="Owner", email="owner@relic.local")
    db_session.add(other)
    db_session.commit()
    grant_access(db_session, other, secret, int(Permission.READ | Permission.WRITE))
    seed_created_file(db_session, secret, other, name="hidden.pdf")

    response = client.get("/api/file-events")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_bearer_token_can_poll_file_events(db_session, root_folder):
    user = UserFactory.build(name="Service", email="service@relic.local")
    db_session.add(user)
    db_session.commit()
    access_key = AccessKeyFactory.build(actor_id=user.id)
    db_session.add(access_key)
    inbox = add_folder(db_session, root_folder, "inbox")
    grant_access(db_session, user, inbox, int(Permission.READ | Permission.WRITE))
    seed_created_file(db_session, inbox, user)
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            response = test_client.get(
                "/api/file-events",
                headers={
                    "Authorization": (
                        f"Bearer {access_key.key_id}:{access_key.secret_access_key}"
                    )
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["event_type"] == "file.created"


def test_admin_sees_all_folder_events(db_session, root_folder):
    admin = UserFactory.build(
        name="Admin",
        email="admin@relic.local",
        role=UserRole.ADMIN,
    )
    alice = UserFactory.build(name="Alice", email="alice@relic.local")
    db_session.add_all([admin, alice])
    db_session.commit()

    secret = add_folder(db_session, root_folder, "secret")
    grant_access(db_session, alice, secret, int(Permission.READ | Permission.WRITE))
    seed_created_file(db_session, secret, alice)
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(admin))
            response = test_client.get("/api/file-events")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
