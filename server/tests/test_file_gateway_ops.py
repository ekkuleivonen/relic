import datetime as dt
import hashlib
import io
import re

import pytest
import settings as S
from api.app import app
from botocore.auth import S3SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from infra.db.engine import get_db
from enums import Permission
from fastapi.testclient import TestClient
from infra.db.models import Base, Blob, File, Folder, FolderAccess
from application.gateway import object_signing
from infra.db.stores.auth import create_session_token
from application.uow_runner import run_with_uow
from infra.maintenance.storage import purge_dereferenced_blobs_batch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import AccessKeyFactory, BucketFactory, UserFactory



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


def create_access_key(db_session, user, *, secret="native-secret"):
    access_key = AccessKeyFactory.build(
        actor_id=user.id,
        key_id="RK_NATIVE_TEST",
        secret_access_key=secret,
    )
    db_session.add(access_key)
    db_session.commit()
    return access_key


def sign_native_s3_request(
    access_key,
    *,
    method: str,
    path: str,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> dict[str, str]:
    request = AWSRequest(
        method=method,
        url=f"http://testserver{path}",
        data=body,
        headers={"Host": "testserver", **(headers or {})},
    )
    S3SigV4Auth(
        Credentials(access_key.key_id, access_key.secret_access_key),
        "s3",
        S.RELIC_SIGNING_REGION,
    ).add_auth(request)
    return dict(request.headers.items())


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

            def head_object(self, Bucket, Key):
                data = store.objects[(Bucket, Key)]
                return {"ContentLength": len(data)}

            def get_object(self, Bucket, Key, Range=None):
                data = store.objects[(Bucket, Key)]
                if Range:
                    match = re.match(r"bytes=(\d+)-(\d*)", Range)
                    if match:
                        start = int(match.group(1))
                        end = int(match.group(2) or len(data) - 1)
                        data = data[start : end + 1]
                return {"Body": FakeStreamingBody(data), "ContentLength": len(data)}

            def delete_object(self, Bucket, Key):
                store.objects.pop((Bucket, Key), None)

        return _Client()


@pytest.fixture()
def fake_storage(monkeypatch):
    store = FakeBucketStore()
    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client",
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
    put_response = client.put(signed["url"], content=content, headers=signed["headers"])
    assert put_response.status_code == 200, put_response.text
    return signed


# ---------------------------------------------------------------------------
# Native Authorization header auth
# ---------------------------------------------------------------------------


def test_native_header_put_creates_file_and_marks_key_used(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    access_key = create_access_key(db_session, user)
    body = b"native cat photo"
    headers = sign_native_s3_request(
        access_key,
        method="PUT",
        path="/s3/photos/native-cat.jpg",
        body=body,
        headers={"x-amz-meta-album": "native"},
    )

    response = client.put("/s3/photos/native-cat.jpg", content=body, headers=headers)

    assert response.status_code == 200, response.text
    db_session.refresh(access_key)
    assert access_key.last_used_at is not None
    file = db_session.scalar(select(File).where(File.name == "native-cat.jpg"))
    assert file is not None
    assert file.actor_id == user.id
    assert file.meta["album"] == "native"
    blob = db_session.get(Blob, file.blob_id)
    assert fake_storage.objects[(physical_bucket.bucket, blob.bucket_key)] == body


def test_native_header_list_head_get_and_delete(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    access_key = create_access_key(db_session, user)

    list_headers = sign_native_s3_request(
        access_key,
        method="GET",
        path="/s3/photos?list-type=2",
    )
    list_response = client.get("/s3/photos?list-type=2", headers=list_headers)
    assert list_response.status_code == 200, list_response.text
    assert "<Key>cat.jpg</Key>" in list_response.text

    head_headers = sign_native_s3_request(
        access_key,
        method="HEAD",
        path="/s3/photos/cat.jpg",
    )
    assert client.head("/s3/photos/cat.jpg", headers=head_headers).status_code == 200

    get_headers = sign_native_s3_request(
        access_key,
        method="GET",
        path="/s3/photos/cat.jpg",
    )
    get_response = client.get("/s3/photos/cat.jpg", headers=get_headers)
    assert get_response.status_code == 200, get_response.text
    assert get_response.content == b"cat photo"

    delete_headers = sign_native_s3_request(
        access_key,
        method="DELETE",
        path="/s3/photos/cat.jpg",
    )
    delete_response = client.delete("/s3/photos/cat.jpg", headers=delete_headers)
    assert delete_response.status_code == 204
    assert db_session.scalar(select(File).where(File.name == "cat.jpg")) is None


def test_native_header_multipart_upload(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    access_key = create_access_key(db_session, user)
    create_headers = sign_native_s3_request(
        access_key,
        method="POST",
        path="/s3/photos/native-large.bin?uploads=",
    )
    create_response = client.post(
        "/s3/photos/native-large.bin?uploads=",
        headers=create_headers,
    )
    assert create_response.status_code == 200, create_response.text
    upload_id = create_response.text.split("<UploadId>", 1)[1].split("</UploadId>", 1)[
        0
    ]

    uploaded_parts = []
    for part_number, content in [(1, b"native "), (2, b"multipart")]:
        path = (
            f"/s3/photos/native-large.bin?partNumber={part_number}&uploadId={upload_id}"
        )
        headers = sign_native_s3_request(
            access_key,
            method="PUT",
            path=path,
            body=content,
        )
        response = client.put(path, content=content, headers=headers)
        assert response.status_code == 200, response.text
        uploaded_parts.append((part_number, response.headers["etag"]))

    complete_body = (
        "<CompleteMultipartUpload>"
        + "".join(
            f"<Part><PartNumber>{part_number}</PartNumber><ETag>{etag}</ETag></Part>"
            for part_number, etag in uploaded_parts
        )
        + "</CompleteMultipartUpload>"
    ).encode()
    complete_path = f"/s3/photos/native-large.bin?uploadId={upload_id}"
    complete_headers = sign_native_s3_request(
        access_key,
        method="POST",
        path=complete_path,
        body=complete_body,
    )
    complete_response = client.post(
        complete_path,
        content=complete_body,
        headers=complete_headers,
    )

    assert complete_response.status_code == 200, complete_response.text
    file = db_session.scalar(select(File).where(File.name == "native-large.bin"))
    assert file is not None
    blob = db_session.get(Blob, file.blob_id)
    assert blob.size_bytes == len(b"native multipart")
    assert (
        fake_storage.objects[(physical_bucket.bucket, blob.bucket_key)]
        == b"native multipart"
    )


def test_native_header_rejects_bad_payload_hash(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    access_key = create_access_key(db_session, user)
    headers = sign_native_s3_request(
        access_key,
        method="PUT",
        path="/s3/photos/bad-hash.jpg",
        body=b"signed body",
    )

    response = client.put(
        "/s3/photos/bad-hash.jpg", content=b"tampered", headers=headers
    )

    assert response.status_code == 403
    assert "XAmzContentSHA256Mismatch" in response.text


def test_native_header_revoked_access_key_is_rejected(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    access_key = create_access_key(db_session, user)
    access_key.revoked_at = dt.datetime.now(dt.UTC)
    db_session.commit()
    headers = sign_native_s3_request(
        access_key,
        method="GET",
        path="/s3/photos?list-type=2",
    )

    response = client.get("/s3/photos?list-type=2", headers=headers)

    assert response.status_code == 403
    assert "InvalidAccessKeyId" in response.text


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
    run_with_uow(
        db_session,
        lambda uow: purge_dereferenced_blobs_batch(
            uow, batch=S.STORAGE_MAINTENANCE_PURGE_BATCH
        ),
    )
    assert db_session.scalar(select(Blob).where(Blob.id == blob_id)) is None
    assert fake_storage.objects == {}


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
    response = client.delete(delete_signed["url"], headers=delete_signed["headers"])
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
    client,
    db_session,
    user,
    photos_folder,
    archives_folder,
    physical_bucket,
    fake_storage,
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
    client,
    db_session,
    user,
    photos_folder,
    archives_folder,
    physical_bucket,
    fake_storage,
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
    client,
    db_session,
    user,
    photos_folder,
    archives_folder,
    physical_bucket,
    fake_storage,
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
    client,
    db_session,
    user,
    photos_folder,
    archives_folder,
    physical_bucket,
    fake_storage,
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
    assert archived.meta["album"] == "winter"


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


def test_presigned_head_returns_ok(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    upload_file(client, photos_folder, filename="cat.jpg", content=b"cat photo")
    signed = object_signing.sign_request_url(
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


def test_multipart_upload_completes_object(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    create = object_signing.sign_request_url(
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
    upload_id = create_response.text.split("<UploadId>", 1)[1].split("</UploadId>", 1)[
        0
    ]
    uploaded_parts = []
    for part_number, content in [(1, b"hello "), (2, b"world")]:
        signed = object_signing.sign_request_url(
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
        assert response.headers["etag"] == f'"{hashlib.md5(content, usedforsecurity=False).hexdigest()}"'
        uploaded_parts.append((part_number, response.headers["etag"]))

    uploads = object_signing.sign_bucket_url(
        method="GET",
        bucket="photos",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"uploads": ""},
    )
    uploads_response = client.get(uploads.url, headers=uploads.headers)
    assert uploads_response.status_code == 200, uploads_response.text
    assert f"<UploadId>{upload_id}</UploadId>" in uploads_response.text
    assert "<Initiated>" in uploads_response.text

    parts = object_signing.sign_request_url(
        method="GET",
        bucket="photos",
        key="large.bin",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"uploadId": upload_id},
    )
    parts_response = client.get(parts.url, headers=parts.headers)
    assert parts_response.status_code == 200, parts_response.text
    assert "<PartNumber>1</PartNumber>" in parts_response.text
    assert "<PartNumber>2</PartNumber>" in parts_response.text

    complete_body = (
        "<CompleteMultipartUpload>"
        + "".join(
            f"<Part><PartNumber>{part_number}</PartNumber><ETag>{etag}</ETag></Part>"
            for part_number, etag in uploaded_parts
        )
        + "</CompleteMultipartUpload>"
    )
    complete = object_signing.sign_request_url(
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
    complete_digest = hashlib.md5(usedforsecurity=False)
    for _part_number, etag in uploaded_parts:
        complete_digest.update(bytes.fromhex(etag.strip('"')))
    assert complete_response.headers["etag"] == f'"{complete_digest.hexdigest()}-2"'
    file = db_session.scalar(select(File).where(File.name == "large.bin"))
    assert file is not None
    blob = db_session.get(Blob, file.blob_id)
    assert blob.size_bytes == len(b"hello world")
    assert (
        fake_storage.objects[(physical_bucket.bucket, blob.bucket_key)]
        == b"hello world"
    )
    assert not [
        key
        for (_bucket, key) in fake_storage.objects
        if key.startswith("__relic_multipart_uploads/")
    ]


def test_multipart_upload_abort_removes_temp_parts(
    client, db_session, user, photos_folder, physical_bucket, fake_storage
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    create = object_signing.sign_request_url(
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
    upload_id = create_response.text.split("<UploadId>", 1)[1].split("</UploadId>", 1)[
        0
    ]
    signed = object_signing.sign_request_url(
        method="PUT",
        bucket="photos",
        key="large.bin",
        headers={},
        user_id=user.id,
        host="testserver",
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"partNumber": "1", "uploadId": upload_id},
    )
    assert (
        client.put(signed.url, content=b"part", headers=signed.headers).status_code
        == 200
    )
    assert any(
        key.startswith("__relic_multipart_uploads/")
        for (_bucket, key) in fake_storage.objects
    )
    abort = object_signing.sign_request_url(
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
    monkeypatch.setattr("infra.auth.s3_signing.now_utc", lambda: frozen)
    presign = client.post("/api/uploads/presign-delete", json={"file_id": str(file.id)})
    signed = presign.json()
    monkeypatch.setattr(
        "infra.auth.s3_signing.now_utc",
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
