import datetime as dt
import hashlib

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
from application.control_plane.auth import create_session_token
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import BucketFactory, UserFactory



@pytest.fixture()
def user(db_session):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def other_user(db_session):
    user = UserFactory.build(email="other@relic.local")
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
def physical_bucket(db_session):
    from tests.factories.models import BucketProbeFactory

    bucket = BucketFactory.build(name="hot")
    db_session.add(bucket)
    db_session.flush()
    db_session.add(BucketProbeFactory.build(bucket_id=bucket.id))
    db_session.commit()
    return bucket


def grant(db_session, user, folder, permissions: int) -> FolderAccess:
    access = FolderAccess(actor_id=user.id, folder_id=folder.id, permissions=permissions)
    db_session.add(access)
    db_session.commit()
    return access


def presign(client: TestClient, folder: Folder, **overrides):
    payload = {
        "folder_id": str(folder.id),
        "filename": "cat.jpg",
        "meta": {"album": "spring"},
    }
    payload.update(overrides)
    return client.post("/api/uploads/presign", json=payload)


def test_presigned_put_creates_file_and_blob(
    client, db_session, user, photos_folder, physical_bucket, monkeypatch
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    uploaded = []

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            if hasattr(Body, "read"):
                Body.seek(0)
                Body = Body.read()
            uploaded.append({"Bucket": Bucket, "Key": Key, "Body": Body})

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )

    response = presign(client, photos_folder)

    assert response.status_code == 200
    signed = response.json()
    assert signed["url"].startswith("/s3/photos/")
    assert signed["headers"]["x-amz-meta-album"] == "spring"
    assert signed["headers"]["x-amz-meta-relic-user"] == str(user.id)

    put_response = client.put(
        signed["url"],
        content=b"cat photo",
        headers=signed["headers"],
    )

    assert put_response.status_code == 200
    digest = hashlib.sha256(b"cat photo").digest()
    assert put_response.headers["etag"] == f'"{digest.hex()}"'
    blob = db_session.scalar(select(Blob).where(Blob.content_hash == digest))
    assert blob is not None
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))
    assert file is not None
    assert file.folder_id == photos_folder.id
    assert file.blob_id == blob.id
    assert file.actor_id == user.id
    assert file.meta == {"album": "spring"}
    assert file.name == "cat.jpg"
    assert blob.mimetype == "image/jpeg"
    assert blob.size_bytes == len(b"cat photo")
    assert uploaded[0]["Bucket"] == "blobs"


def test_presign_requires_write_permission(client, db_session, user, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))

    response = presign(client, photos_folder)

    assert response.status_code == 403


def test_put_rechecks_write_permission(
    client, db_session, user, photos_folder, physical_bucket, monkeypatch
):
    access = grant(
        db_session, user, photos_folder, int(Permission.READ | Permission.WRITE)
    )

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            raise AssertionError("revoked upload should not reach storage")

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )
    response = presign(client, photos_folder)
    assert response.status_code == 200
    signed = response.json()
    access.permissions = int(Permission.READ)
    db_session.commit()

    put_response = client.put(
        signed["url"],
        content=b"cat photo",
        headers=signed["headers"],
    )

    assert put_response.status_code == 403
    assert "AccessDenied" in put_response.text


def test_tampered_signature_fails(client, db_session, user, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    response = presign(client, photos_folder)
    signed = response.json()
    tampered_url = signed["url"].replace("X-Amz-Signature=", "X-Amz-Signature=0")

    put_response = client.put(
        tampered_url,
        content=b"cat photo",
        headers=signed["headers"],
    )

    assert put_response.status_code == 403
    assert "SignatureDoesNotMatch" in put_response.text


def test_tampered_signed_metadata_header_fails(client, db_session, user, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    response = presign(client, photos_folder)
    signed = response.json()
    headers = dict(signed["headers"])
    headers["x-amz-meta-album"] = "summer"

    put_response = client.put(signed["url"], content=b"cat photo", headers=headers)

    assert put_response.status_code == 403
    assert "SignatureDoesNotMatch" in put_response.text


def test_expired_url_fails(client, db_session, user, photos_folder, monkeypatch):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    frozen = dt.datetime(2026, 5, 9, 0, 0, tzinfo=dt.UTC)
    monkeypatch.setattr("application.gateway.object_signing.now_utc", lambda: frozen)
    response = presign(client, photos_folder)
    signed = response.json()
    monkeypatch.setattr(
        "application.gateway.object_signing.now_utc",
        lambda: frozen + dt.timedelta(minutes=6),
    )

    put_response = client.put(
        signed["url"],
        content=b"cat photo",
        headers=signed["headers"],
    )

    assert put_response.status_code == 403
    assert "SignatureDoesNotMatch" in put_response.text


def test_replayed_url_hits_file_unique_constraint(
    client, db_session, user, photos_folder, physical_bucket, monkeypatch
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            if hasattr(Body, "read"):
                Body.seek(0)
                Body = Body.read()
            return None

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )
    response = presign(client, photos_folder)
    signed = response.json()

    first = client.put(signed["url"], content=b"cat photo", headers=signed["headers"])
    second = client.put(signed["url"], content=b"cat photo", headers=signed["headers"])

    assert first.status_code == 200
    assert second.status_code == 409
    assert "BucketAlreadyExists" in second.text or "Conflict" in second.text


def test_unsigned_gateway_put_is_rejected(client):
    response = client.put("/s3/photos/cat.jpg", content=b"cat")

    assert response.status_code == 400
    assert "AuthorizationHeaderMalformed" in response.text


def test_unknown_signing_key_is_rejected(client, db_session, user, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    response = presign(client, photos_folder)
    signed = response.json()
    tampered_url = signed["url"].replace(
        "Credential=relic-dev%2F",
        "Credential=missing%2F",
    )

    put_response = client.put(
        tampered_url,
        content=b"cat photo",
        headers=signed["headers"],
    )

    assert put_response.status_code == 403
    assert "InvalidAccessKeyId" in put_response.text


def test_server_signed_and_stub_user_key_use_same_gateway_path(
    client, db_session, user, photos_folder, physical_bucket, monkeypatch
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))

    stored = []

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            if hasattr(Body, "read"):
                Body.seek(0)
                Body = Body.read()
            stored.append(Body)

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )
    response = presign(client, photos_folder, filename="cat.jpg")
    signed = response.json()

    first = client.put(signed["url"], content=b"cat photo", headers=signed["headers"])
    monkeypatch.setattr(
        "settings.RELIC_SIGNING_KEYS",
        {
            "relic-dev": "dev-encryption-secret-change-me:s3-signing",
            "user-fixture": "fixture-user-secret",
        },
    )
    monkeypatch.setattr("settings.RELIC_SIGNING_CURRENT_KEY_ID", "user-fixture")
    response = presign(client, photos_folder, filename="dog.jpg")
    user_signed = response.json()
    second = client.put(
        user_signed["url"],
        content=b"dog photo",
        headers=user_signed["headers"],
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(stored) == 2
