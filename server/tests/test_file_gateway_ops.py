import datetime as dt
import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
import settings as S
from models import AuditEvent, Base, Blob, File, Folder, FolderAccess
from schema_plan import BucketTier, Permission
from services.auth import create_session_token
from services import s3_signing
from services.storage_maintenance import purge_dereferenced_blobs_batch
from tests.factories.models import BucketFactory, UserFactory


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
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(root)
    db_session.commit()
    return root


@pytest.fixture()
def photos_folder(db_session, root_folder):
    folder = Folder(
        name="photos",
        parent_id=root_folder.id,
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


@pytest.fixture()
def archives_folder(db_session, root_folder):
    folder = Folder(
        name="archives",
        parent_id=root_folder.id,
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


@pytest.fixture()
def physical_bucket(db_session):
    bucket = BucketFactory.build(name="hot")
    bucket.probe_latency_put_ms = 10
    bucket.probe_latency_head_ms = 10
    bucket.probe_latency_get_ms = 10
    bucket.probe_latency_delete_ms = 10
    db_session.add(bucket)
    db_session.commit()
    return bucket


def grant(db_session, user, folder, permissions: int) -> FolderAccess:
    access = FolderAccess(
        user_id=user.id, folder_id=folder.id, permissions=permissions
    )
    db_session.add(access)
    db_session.commit()
    return access


class FakeStreamingBody:
    def __init__(self, data: bytes):
        self._buffer = io.BytesIO(data)

    def read(self, size=-1):
        return self._buffer.read(size)


class FakeBucketStore:
    """In-memory fake of a bucket; supports put/get/delete."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def make_client(self):
        store = self

        class _Client:
            def put_object(self, Bucket, Key, Body):
                if hasattr(Body, "read"):
                    Body.seek(0)
                    Body = Body.read()
                store.objects[(Bucket, Key)] = Body

            def get_object(self, Bucket, Key, Range=None):
                data = store.objects[(Bucket, Key)]
                if Range:
                    return {
                        "Body": FakeStreamingBody(data),
                        "ContentLength": len(data),
                        "ContentRange": f"bytes 0-{len(data) - 1}/{len(data)}",
                    }
                return {"Body": FakeStreamingBody(data), "ContentLength": len(data)}

            def delete_object(self, Bucket, Key):
                store.objects.pop((Bucket, Key), None)

        return _Client()


@pytest.fixture()
def fake_storage(monkeypatch):
    store = FakeBucketStore()
    monkeypatch.setattr(
        "services.objects.boto3.client",
        lambda **kwargs: store.make_client(),
    )
    return store


def upload_file(client, folder, *, filename, content):
    presign = client.post(
        "/api/uploads/presign",
        json={
            "folder_id": str(folder.id),
            "filename": filename,
            "meta": {},
        },
    )
    assert presign.status_code == 200, presign.text
    signed = presign.json()
    put_response = client.put(
        signed["url"], content=content, headers=signed["headers"]
    )
    assert put_response.status_code == 200, put_response.text
    return signed


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_presigned_delete_drops_file_and_blob(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))
    assert file is not None
    blob_id = file.blob_id

    presign = client.post(
        "/api/uploads/presign-delete",
        json={"file_id": str(file.id)},
    )
    assert presign.status_code == 200, presign.text
    signed = presign.json()

    response = client.delete(signed["url"], headers=signed["headers"])
    assert response.status_code == 204
    assert db_session.scalar(select(File).where(File.id == file.id)) is None
    purge_dereferenced_blobs_batch(db_session, batch=S.STORAGE_MAINTENANCE_PURGE_BATCH)
    assert db_session.scalar(select(Blob).where(Blob.id == blob_id)) is None
    assert fake_storage.objects == {}
    assert db_session.scalars(select(AuditEvent)).all() == []


def test_delete_idempotent_on_missing_key(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    presign = client.post(
        "/api/uploads/presign-delete",
        json={"file_id": str(file.id)},
    )
    signed = presign.json()
    first = client.delete(signed["url"], headers=signed["headers"])
    second = client.delete(signed["url"], headers=signed["headers"])
    assert first.status_code == 204
    assert second.status_code == 204
    assert db_session.scalars(select(AuditEvent)).all() == []


def test_delete_keeps_blob_when_other_files_share_it(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    content = b"shared photo"
    upload_file(client, photos_folder, filename="cat.jpg", content=content)
    file_a = db_session.scalar(select(File).where(File.name == "cat.jpg"))
    blob = db_session.get(Blob, file_a.blob_id)
    assert blob.refcount == 1

    presign = client.post(
        "/api/uploads/presign-copy",
        json={
            "source_file_id": str(file_a.id),
            "destination_folder_id": str(photos_folder.id),
            "name": "cat-copy.jpg",
            "metadata_directive": "COPY",
        },
    )
    assert presign.status_code == 200, presign.text
    signed = presign.json()
    copy_response = client.put(signed["url"], headers=signed["headers"])
    assert copy_response.status_code == 200, copy_response.text

    db_session.refresh(blob)
    assert blob.refcount == 2

    delete_presign = client.post(
        "/api/uploads/presign-delete",
        json={"file_id": str(file_a.id)},
    )
    delete_signed = delete_presign.json()
    response = client.delete(
        delete_signed["url"], headers=delete_signed["headers"]
    )
    assert response.status_code == 204

    db_session.refresh(blob)
    assert blob.refcount == 1
    assert fake_storage.objects, "blob bytes should remain while refcount > 0"


def test_presign_delete_requires_delete_permission(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    response = client.post(
        "/api/uploads/presign-delete",
        json={"file_id": str(file.id)},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# COPY
# ---------------------------------------------------------------------------


def test_presigned_copy_creates_file_and_bumps_refcount(
    client, db_session, user, photos_folder, archives_folder, physical_bucket, fake_storage
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE),
    )
    grant(
        db_session,
        user,
        archives_folder,
        int(Permission.READ | Permission.WRITE),
    )
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    source_file = db_session.scalar(select(File).where(File.name == "cat.jpg"))
    blob = db_session.get(Blob, source_file.blob_id)
    assert blob.refcount == 1

    presign = client.post(
        "/api/uploads/presign-copy",
        json={
            "source_file_id": str(source_file.id),
            "destination_folder_id": str(archives_folder.id),
            "name": "cat.jpg",
            "metadata_directive": "COPY",
        },
    )
    assert presign.status_code == 200, presign.text
    signed = presign.json()
    response = client.put(signed["url"], headers=signed["headers"])
    assert response.status_code == 200, response.text
    digest = hashlib.sha256(b"cat photo").hexdigest()
    assert response.headers["etag"] == f'"{digest}"'

    archived = db_session.scalar(
        select(File).where(File.folder_id == archives_folder.id, File.name == "cat.jpg")
    )
    assert archived is not None
    assert archived.blob_id == source_file.blob_id

    db_session.refresh(blob)
    assert blob.refcount == 2


def test_presign_copy_requires_write_on_destination(
    client, db_session, user, photos_folder, archives_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    grant(db_session, user, archives_folder, int(Permission.READ))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    source_file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    response = client.post(
        "/api/uploads/presign-copy",
        json={
            "source_file_id": str(source_file.id),
            "destination_folder_id": str(archives_folder.id),
            "name": "cat.jpg",
            "metadata_directive": "COPY",
        },
    )
    assert response.status_code == 403


def test_presign_copy_to_other_folder(
    client, db_session, user, photos_folder, archives_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    source_file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    response = client.post(
        "/api/uploads/presign-copy",
        json={
            "source_file_id": str(source_file.id),
            "destination_folder_id": str(archives_folder.id),
            "name": "cat.jpg",
            "metadata_directive": "COPY",
        },
    )
    assert response.status_code == 200


def test_presigned_copy_replace_directive_overrides_meta(
    client, db_session, user, photos_folder, archives_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    source_file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    presign = client.post(
        "/api/uploads/presign-copy",
        json={
            "source_file_id": str(source_file.id),
            "destination_folder_id": str(archives_folder.id),
            "name": "cat.jpg",
            "metadata_directive": "REPLACE",
            "meta": {"album": "winter"},
        },
    )
    assert presign.status_code == 200, presign.text
    signed = presign.json()
    response = client.put(signed["url"], headers=signed["headers"])
    assert response.status_code == 200, response.text

    archived = db_session.scalar(
        select(File).where(File.folder_id == archives_folder.id)
    )
    assert archived.meta["kvs"]["album"] == "winter"


# ---------------------------------------------------------------------------
# DOWNLOAD
# ---------------------------------------------------------------------------


def test_presigned_download_streams_bytes(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    presign = client.post(
        "/api/uploads/presign-download",
        json={"file_id": str(file.id)},
    )
    assert presign.status_code == 200, presign.text
    signed = presign.json()

    response = client.get(signed["url"], headers=signed["headers"])
    assert response.status_code == 200
    assert response.content == b"cat photo"
    digest = hashlib.sha256(b"cat photo").hexdigest()
    assert response.headers["etag"] == f'"{digest}"'
    assert response.headers["content-type"] == "image/jpeg"
    assert (
        db_session.scalar(
            select(AuditEvent).where(AuditEvent.operation == "object.get")
        )
        is None
    )


def test_presigned_head_does_not_emit_audit_event(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    signed = s3_signing.sign_request_url(
        method="HEAD",
        bucket="photos",
        key="cat.jpg",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
    )

    response = client.head(signed.url, headers=signed.headers)
    assert response.status_code == 200
    assert (
        db_session.scalar(
            select(AuditEvent).where(AuditEvent.operation == "object.head")
        )
        is None
    )


def test_multipart_upload_completes_object(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    create = s3_signing.sign_request_url(
        method="POST",
        bucket="photos",
        key="large.bin",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"uploads": ""},
    )

    create_response = client.post(create.url, headers=create.headers)

    assert create_response.status_code == 200, create_response.text
    upload_id = create_response.text.split("<UploadId>", 1)[1].split("</UploadId>", 1)[0]
    uploaded_parts = []
    for part_number, content in [(1, b"hello "), (2, b"world")]:
        signed = s3_signing.sign_request_url(
            method="PUT",
            bucket="photos",
            key="large.bin",
            headers={},
            user_id=user.id,
            host="testserver",
            ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
            query_params={"partNumber": str(part_number), "uploadId": upload_id},
        )
        response = client.put(signed.url, content=content, headers=signed.headers)
        assert response.status_code == 200, response.text
        uploaded_parts.append((part_number, response.headers["etag"]))

    complete_body = (
        "<CompleteMultipartUpload>"
        + "".join(
            f"<Part><PartNumber>{part_number}</PartNumber><ETag>{etag}</ETag></Part>"
            for part_number, etag in uploaded_parts
        )
        + "</CompleteMultipartUpload>"
    )
    complete = s3_signing.sign_request_url(
        method="POST",
        bucket="photos",
        key="large.bin",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"uploadId": upload_id},
    )

    complete_response = client.post(
        complete.url, content=complete_body, headers=complete.headers
    )

    assert complete_response.status_code == 200, complete_response.text
    file = db_session.scalar(select(File).where(File.name == "large.bin"))
    assert file is not None
    blob = db_session.get(Blob, file.blob_id)
    assert blob.size_bytes == len(b"hello world")
    assert fake_storage.objects[(physical_bucket.bucket, blob.bucket_key)] == b"hello world"
    assert not [
        key
        for (_bucket, key) in fake_storage.objects
        if key.startswith("__relic_multipart_uploads/")
    ]


def test_multipart_upload_abort_removes_temp_parts(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    create = s3_signing.sign_request_url(
        method="POST",
        bucket="photos",
        key="large.bin",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"uploads": ""},
    )
    create_response = client.post(create.url, headers=create.headers)
    upload_id = create_response.text.split("<UploadId>", 1)[1].split("</UploadId>", 1)[0]
    signed = s3_signing.sign_request_url(
        method="PUT",
        bucket="photos",
        key="large.bin",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"partNumber": "1", "uploadId": upload_id},
    )
    assert client.put(signed.url, content=b"part", headers=signed.headers).status_code == 200
    assert any(
        key.startswith("__relic_multipart_uploads/")
        for (_bucket, key) in fake_storage.objects
    )
    abort = s3_signing.sign_request_url(
        method="DELETE",
        bucket="photos",
        key="large.bin",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"uploadId": upload_id},
    )

    response = client.delete(abort.url, headers=abort.headers)

    assert response.status_code == 204
    assert fake_storage.objects == {}
    assert db_session.scalar(select(File).where(File.name == "large.bin")) is None


def test_presigned_download_passes_range_header(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    presign = client.post(
        "/api/uploads/presign-download",
        json={"file_id": str(file.id)},
    )
    signed = presign.json()
    headers = {**signed["headers"], "Range": "bytes=0-3"}
    response = client.get(signed["url"], headers=headers)
    assert response.status_code == 206
    assert "content-range" in {key.lower() for key in response.headers.keys()}


def test_presign_download_requires_read_permission(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    other = UserFactory.build(email="other@relic.local")
    db_session.add(other)
    db_session.commit()
    client.cookies.set("relic_session", create_session_token(other))

    response = client.post(
        "/api/uploads/presign-download",
        json={"file_id": str(file.id)},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tamper / expiry parity checks
# ---------------------------------------------------------------------------


def test_delete_url_expired(
    client, db_session, user, photos_folder, physical_bucket, fake_storage, monkeypatch
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    frozen = dt.datetime(2026, 5, 9, 0, 0, tzinfo=dt.UTC)
    monkeypatch.setattr("services.s3_signing.now_utc", lambda: frozen)
    presign = client.post(
        "/api/uploads/presign-delete", json={"file_id": str(file.id)}
    )
    signed = presign.json()
    monkeypatch.setattr(
        "services.s3_signing.now_utc",
        lambda: frozen + dt.timedelta(minutes=10),
    )
    response = client.delete(signed["url"], headers=signed["headers"])
    assert response.status_code == 403
    assert "SignatureDoesNotMatch" in response.text


def test_get_url_tampered_signature_fails(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    file = db_session.scalar(select(File).where(File.name == "cat.jpg"))

    presign = client.post(
        "/api/uploads/presign-download", json={"file_id": str(file.id)}
    )
    signed = presign.json()
    tampered_url = signed["url"].replace("X-Amz-Signature=", "X-Amz-Signature=0")
    response = client.get(tampered_url, headers=signed["headers"])
    assert response.status_code == 403
    assert "SignatureDoesNotMatch" in response.text
