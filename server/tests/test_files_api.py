import uuid

import pytest
from api.app import app
from infra.db.engine import get_db
from enums import Permission
from fastapi.testclient import TestClient
from infra.db.models import (
    Base,
    Blob,
    File,
    Folder,
    FolderAccess,
)
from infra.db.stores.auth import create_session_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import StorageBackendFactory, UserFactory



@pytest.fixture()
def user(db_session):
    user = UserFactory.build(email="user@relic.local")
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
    root = Folder(
        name="",
        parent_id=None,
    )
    db_session.add(root)
    db_session.commit()
    return root


@pytest.fixture()
def photos_folder(db_session, root_folder):
    folder = Folder(
        name="photos",
        parent_id=root_folder.id,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


@pytest.fixture()
def archives_folder(db_session, root_folder):
    folder = Folder(
        name="archives",
        parent_id=root_folder.id,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


@pytest.fixture()
def physical_bucket(db_session):
    from tests.factories.models import StorageBackendProbeFactory

    bucket = StorageBackendFactory.build(name="hot")
    db_session.add(bucket)
    db_session.flush()
    db_session.add(StorageBackendProbeFactory.build(storage_backend_id=bucket.id))
    db_session.commit()
    return bucket


def grant(db_session, user, folder, permissions: int) -> FolderAccess:
    access = FolderAccess(actor_id=user.id, folder_id=folder.id, permissions=permissions)
    db_session.add(access)
    db_session.commit()
    return access


def make_file(db_session, *, folder, blob, name, user, meta=None):
    meta = meta or {}
    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        actor_id=user.id,
        name=name,
        meta=meta,
    )
    db_session.add(file)
    db_session.commit()
    return file


def make_blob(db_session, *, bucket, content_hash):
    blob = Blob(
        storage_backend_id=bucket.id,
        bucket_key="2026/05/09/blob",
        content_hash=content_hash,
        size_bytes=9,
        refcount=1,
    )
    db_session.add(blob)
    db_session.commit()
    return blob


# ---------------------------------------------------------------------------
# Gateway location on FileRead
# ---------------------------------------------------------------------------


def test_get_file_includes_gateway_location_for_flat_folder(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(50).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.get(f"/api/files/{file.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["gateway"] == {
        "bucket": "relic",
        "key": "photos/cat.jpg",
        "object_uri": "/s3/relic/photos/cat.jpg",
    }


def test_get_file_includes_gateway_location_for_nested_folder(
    client, db_session, user, root_folder, physical_bucket
):
    local_testing = Folder(name="Local Testing", parent_id=root_folder.id)
    db_session.add(local_testing)
    db_session.commit()
    era_a = Folder(name="era-a", parent_id=local_testing.id)
    db_session.add(era_a)
    db_session.commit()
    grant(db_session, user, era_a, int(Permission.READ))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(51).to_bytes(32, "big")
    )
    file = make_file(
        db_session,
        user=user,
        folder=era_a,
        blob=blob,
        name="account-statement.csv",
    )

    response = client.get(f"/api/files/{file.id}")
    assert response.status_code == 200, response.text
    assert response.json()["gateway"] == {
        "bucket": "relic",
        "key": "Local Testing/era-a/account-statement.csv",
        "object_uri": "/s3/relic/Local%20Testing/era-a/account-statement.csv",
    }


def test_rename_updates_gateway_key(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(52).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.patch(f"/api/files/{file.id}", json={"name": "feline.jpg"})
    assert response.status_code == 200, response.text
    assert response.json()["gateway"]["key"] == "photos/feline.jpg"
    assert response.json()["gateway"]["object_uri"] == "/s3/relic/photos/feline.jpg"


def test_list_files_includes_gateway_on_each_item(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(53).to_bytes(32, "big")
    )
    make_file(db_session, user=user, folder=photos_folder, blob=blob, name="a.jpg")

    response = client.get(f"/api/files/?folder_id={photos_folder.id}")
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["gateway"]["bucket"] == "relic"
    assert item["gateway"]["key"] == "photos/a.jpg"


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------


def test_move_file_changes_folder_id(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(1).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["folder_id"] == str(archives_folder.id)

    db_session.refresh(file)
    assert file.folder_id == archives_folder.id
    db_session.refresh(blob)
    assert blob.refcount == 1


def test_move_file_to_other_folder(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(2).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 200


def test_move_requires_delete_on_source(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(3).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 403


def test_move_requires_write_on_destination(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(4).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 403


def test_move_conflicts_when_name_taken_in_destination(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob_a = make_blob(
        db_session, bucket=physical_bucket, content_hash=(5).to_bytes(32, "big")
    )
    blob_b = make_blob(
        db_session, bucket=physical_bucket, content_hash=(6).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob_a, name="cat.jpg"
    )
    make_file(
        db_session, user=user, folder=archives_folder, blob=blob_b, name="cat.jpg"
    )

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def test_rename_file_in_place(client, db_session, user, photos_folder, physical_bucket):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(7).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.patch(
        f"/api/files/{file.id}",
        json={"name": "feline.jpg"},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(file)
    assert file.name == "feline.jpg"


def test_rename_restores_extension_when_omitted(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(17).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.patch(
        f"/api/files/{file.id}",
        json={"name": "feline"},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(file)
    assert file.name == "feline.jpg"


def test_move_with_new_name_restores_extension_when_omitted(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(18).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.post(
        f"/api/files/{file.id}/move",
        json={
            "destination_folder_id": str(archives_folder.id),
            "name": "feline",
        },
    )
    assert response.status_code == 200, response.text
    db_session.refresh(file)
    assert file.name == "feline.jpg"
    assert file.folder_id == archives_folder.id


def test_rename_conflicts_with_existing_name(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    blob_a = make_blob(
        db_session, bucket=physical_bucket, content_hash=(8).to_bytes(32, "big")
    )
    blob_b = make_blob(
        db_session, bucket=physical_bucket, content_hash=(9).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob_a, name="cat.jpg"
    )
    make_file(db_session, user=user, folder=photos_folder, blob=blob_b, name="dog.jpg")

    response = client.patch(
        f"/api/files/{file.id}",
        json={"name": "dog.jpg"},
    )
    assert response.status_code == 409


def test_rename_requires_write(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(10).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg"
    )

    response = client.patch(
        f"/api/files/{file.id}",
        json={"name": "feline.jpg"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Single delete
# ---------------------------------------------------------------------------


def test_delete_file(client, db_session, user, photos_folder, physical_bucket):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(40).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="remove.jpg"
    )

    response = client.delete(f"/api/files/{file.id}")
    assert response.status_code == 204, response.text

    db_session.refresh(blob)
    assert blob.refcount == 0
    assert db_session.get(type(file), file.id) is None


def test_delete_file_returns_not_found_for_missing_id(
    client, db_session, user, photos_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.DELETE))
    missing_id = uuid.uuid4()

    response = client.delete(f"/api/files/{missing_id}")
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------


def test_bulk_delete_removes_files_and_decrements_refcount(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    blob_a = make_blob(
        db_session, bucket=physical_bucket, content_hash=(20).to_bytes(32, "big")
    )
    blob_b = make_blob(
        db_session, bucket=physical_bucket, content_hash=(21).to_bytes(32, "big")
    )
    file_a = make_file(
        db_session, user=user, folder=photos_folder, blob=blob_a, name="a.jpg"
    )
    file_b = make_file(
        db_session, user=user, folder=photos_folder, blob=blob_b, name="b.jpg"
    )

    response = client.post(
        "/api/files/bulk-delete",
        json={"file_ids": [str(file_a.id), str(file_b.id)]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["deleted_ids"]) == {str(file_a.id), str(file_b.id)}
    assert body["errors"] == []

    db_session.refresh(blob_a)
    db_session.refresh(blob_b)
    assert blob_a.refcount == 0
    assert blob_b.refcount == 0


def test_bulk_delete_reports_per_file_errors(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(22).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="keep.jpg"
    )
    missing_id = uuid.uuid4()

    response = client.post(
        "/api/files/bulk-delete",
        json={"file_ids": [str(file.id), str(missing_id)]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted_ids"] == [str(file.id)]
    assert len(body["errors"]) == 1
    assert body["errors"][0]["file_id"] == str(missing_id)


def test_bulk_move_files(client, db_session, user, photos_folder, archives_folder, physical_bucket):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(30).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="move-me.jpg"
    )

    response = client.post(
        "/api/files/bulk-move",
        json={
            "file_ids": [str(file.id)],
            "destination_folder_id": str(archives_folder.id),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["moved_ids"] == [str(file.id)]
    db_session.refresh(file)
    assert file.folder_id == archives_folder.id


def test_bulk_update_meta(client, db_session, user, photos_folder, physical_bucket):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.ENRICH),
    )
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(31).to_bytes(32, "big")
    )
    file = make_file(
        db_session, user=user, folder=photos_folder, blob=blob, name="meta.jpg"
    )

    response = client.post(
        "/api/files/bulk-update",
        json={"file_ids": [str(file.id)], "meta": {"tags": ["updated"]}},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(file)
    assert file.meta["tags"] == ["updated"]
