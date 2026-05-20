import hashlib
import re
import uuid as uuid_module

import pytest
from api.app import app
from infra.db.engine import get_db
from enums import Permission, UserRole
from fastapi.testclient import TestClient
from domain.exceptions import ConflictError, ResourceNotFound
from infra.db.models import (
    Base,
    Blob,
    Bucket,
    File,
    Folder,
    FolderAccess,
)
from infra.gateway import object_writes
from infra.db.stores.placement import choose_bucket, clear_bucket_usage_cache, get_bucket_usage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import (
    BlobFactory,
    BucketFactory,
    BucketProbeFactory,
    UserFactory,
)


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
    root = Folder(
        name="",
        parent_id=None,
    )
    db_session.add(root)
    db_session.commit()
    return root


@pytest.fixture()
def bucket_folder(db_session, root_folder):
    folder = Folder(
        name="photos",
        parent_id=root_folder.id,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


def add_bucket(db_session, **overrides) -> Bucket:
    bucket = BucketFactory.build(**overrides)
    db_session.add(bucket)
    db_session.commit()
    db_session.refresh(bucket)
    return bucket


def mark_healthy(bucket: Bucket, latency: int = 10, db_session=None) -> None:
    """Insert a successful probe sample so hotness ranking picks the bucket up."""
    if db_session is None:
        raise RuntimeError("db_session is required to record a probe sample")
    db_session.add(
        BucketProbeFactory.build(
            bucket_id=bucket.id,
            put_ms=latency,
            head_ms=latency,
            get_ms=latency,
            delete_ms=latency,
        )
    )


def read_body(body):
    if hasattr(body, "read"):
        body.seek(0)
        return body.read()
    return body


def test_choose_bucket_filters_capacity_and_prefers_latency(db_session):
    full = add_bucket(
        db_session,
        name="full",
        max_size_bytes=10,
    )
    slow = add_bucket(db_session, name="slow")
    fast = add_bucket(db_session, name="fast")
    db_session.add(BlobFactory.build(bucket_id=full.id, size_bytes=9))
    mark_healthy(full, 1, db_session=db_session)
    mark_healthy(slow, 50, db_session=db_session)
    mark_healthy(fast, 5, db_session=db_session)
    db_session.commit()

    chosen = choose_bucket(db_session, size_bytes=2)

    assert chosen.id == fast.id


def test_choose_bucket_raises_when_no_bucket_has_capacity(db_session):
    bucket = add_bucket(
        db_session,
        name="tiny",
        max_size_bytes=3,
    )
    db_session.add(BlobFactory.build(bucket_id=bucket.id, size_bytes=3))
    mark_healthy(bucket, db_session=db_session)
    db_session.commit()

    with pytest.raises(ConflictError):
        choose_bucket(db_session, size_bytes=1)


def test_choose_bucket_honors_preferred_bucket_when_it_fits(db_session):
    fast = add_bucket(db_session, name="fast")
    preferred = add_bucket(db_session, name="preferred")
    mark_healthy(fast, 1, db_session=db_session)
    mark_healthy(preferred, 100, db_session=db_session)
    db_session.commit()

    chosen = choose_bucket(
        db_session, size_bytes=1, preferred_bucket_id=preferred.id
    )

    assert chosen.id == preferred.id


def test_choose_bucket_falls_back_when_preferred_is_full(db_session):
    fallback = add_bucket(db_session, name="fallback")
    preferred = add_bucket(db_session, name="preferred", max_size_bytes=2)
    db_session.add(BlobFactory.build(bucket_id=preferred.id, size_bytes=2))
    mark_healthy(fallback, 100, db_session=db_session)
    mark_healthy(preferred, 1, db_session=db_session)
    db_session.commit()

    chosen = choose_bucket(
        db_session, size_bytes=1, preferred_bucket_id=preferred.id
    )

    assert chosen.id == fallback.id


def test_put_object_uploads_new_blob_and_creates_file(
    db_session, bucket_folder, monkeypatch, storage_registry
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket, db_session=db_session)
    db_session.commit()
    body = b"cat photo"
    uploaded = []

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            Body = read_body(Body)
            uploaded.append({"Bucket": Bucket, "Key": Key, "Body": Body})

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )

    user = UserFactory.build(email="user@relic.local", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    result = object_writes.put_object(
        db_session,
        storage=storage_registry,
        bucket_name="photos",
        key="2026/cat.jpg",
        body=body,
        ingest_meta={"album": "spring"},
        current_user=user,
    )

    digest = hashlib.sha256(body).digest()
    digest_hex = digest.hex()
    assert result.etag == digest_hex
    assert len(uploaded) == 1
    assert uploaded[0]["Bucket"] == "blobs"
    assert uploaded[0]["Body"] == body
    assert re.fullmatch(
        r"\d{4}/\d{2}/\d{2}/[0-9a-f-]{36}",
        uploaded[0]["Key"],
    )
    assert uploaded == [
        {
            "Bucket": "blobs",
            "Key": uploaded[0]["Key"],
            "Body": body,
        }
    ]

    blob = db_session.scalar(select(Blob).where(Blob.content_hash == digest))
    assert blob is not None
    assert blob.bucket_key == uploaded[0]["Key"]
    assert blob.refcount == 1
    assert blob.bucket_id == physical_bucket.id
    assert blob.size_bytes == len(body)
    usage = get_bucket_usage(db_session, physical_bucket.id)
    assert usage.object_count == 1
    assert usage.current_size_bytes == len(body)

    child_folder = db_session.scalar(
        select(Folder).where(
            Folder.parent_id == bucket_folder.id, Folder.name == "2026"
        )
    )
    assert child_folder is not None
    file = db_session.scalar(select(File).where(File.folder_id == child_folder.id))
    assert file is not None
    assert file.name == "cat.jpg"
    assert file.blob_id == blob.id
    assert file.actor_id == user.id
    assert file.meta == {"album": "spring"}
    assert blob.mimetype == "image/jpeg"
    assert blob.extension == "jpg"


def test_put_object_passes_inherited_preferred_bucket_to_choose_bucket(
    db_session, root_folder, monkeypatch, storage_registry
):
    physical_cold = add_bucket(db_session, name="cold")
    mark_healthy(physical_cold, db_session=db_session)
    root_folder.preferred_bucket_id = physical_cold.id
    bucket_folder = Folder(
        name="archive",
        parent_id=root_folder.id,
    )
    db_session.add(bucket_folder)
    db_session.commit()

    captured: list[uuid_module.UUID | None] = []

    def fake_choose(db, *, size_bytes, preferred_bucket_id=None, **_kwargs):
        captured.append(preferred_bucket_id)
        return physical_cold

    monkeypatch.setattr("infra.gateway.object_writes.choose_bucket", fake_choose)

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )

    user = UserFactory.build(email="user@relic.local", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()

    body = b"z"
    object_writes.put_object(
        db_session,
        storage=storage_registry,
        bucket_name="archive",
        key="2026/a.jpg",
        body=body,
        ingest_meta={},
        current_user=user,
    )

    assert captured == [physical_cold.id]


def test_put_object_dedupes_existing_blob(
    db_session, bucket_folder, monkeypatch, storage_registry
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket, db_session=db_session)
    body = b"same bytes"
    blob = BlobFactory(
        bucket_id=physical_bucket.id,
        content_hash=hashlib.sha256(body).digest(),
        refcount=1,
    )
    db_session.add(blob)
    db_session.commit()

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            raise AssertionError("duplicate content should not be uploaded")

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )

    user = UserFactory.build(email="user@relic.local", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    result = object_writes.put_object(
        db_session,
        storage=storage_registry,
        bucket_name="photos",
        key="copy.txt",
        body=body,
        ingest_meta={},
        current_user=user,
    )

    assert result.file.name == "copy.txt"
    db_session.refresh(blob)
    assert blob.refcount == 2
    usage = get_bucket_usage(db_session, physical_bucket.id)
    assert usage.object_count == 1
    assert usage.current_size_bytes == blob.size_bytes


def test_put_object_overwrites_existing_file_name(
    db_session, root_folder, bucket_folder, monkeypatch, storage_registry
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket, db_session=db_session)
    old_blob = BlobFactory(bucket_id=physical_bucket.id, refcount=1)
    owner = UserFactory.build(email="owner@relic.local", role=UserRole.ADMIN)
    db_session.add(owner)
    db_session.add(old_blob)
    db_session.flush()
    existing_file = File(
        folder_id=bucket_folder.id,
        blob_id=old_blob.id,
        actor_id=owner.id,
        name="cat.jpg",
        meta={},
    )
    db_session.add(existing_file)
    db_session.commit()
    body = b"new"
    uploaded = []

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            uploaded.append({"Bucket": Bucket, "Key": Key, "Body": read_body(Body)})

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )

    result = object_writes.put_object(
        db_session,
        storage=storage_registry,
        bucket_name="photos",
        key="cat.jpg",
        body=body,
        ingest_meta={"album": "summer"},
        current_user=owner,
    )

    assert len(uploaded) == 1
    assert result.file.id == existing_file.id
    assert result.file.blob_id != old_blob.id
    assert result.file.meta["album"] == "summer"
    db_session.refresh(old_blob)
    assert old_blob.refcount == 0
    assert result.blob.mimetype == "image/jpeg"
    assert result.blob.extension == "jpg"


def test_put_object_with_user_requires_write_permission(
    db_session, bucket_folder, storage_registry
):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()

    with pytest.raises(ResourceNotFound):
        object_writes.put_object(
            db_session,
            storage=storage_registry,
            bucket_name="photos",
            key="cat.jpg",
            body=b"cat",
            ingest_meta={},
            current_user=user,
        )


def test_put_object_with_admin_user_bypasses_folder_access(
    db_session, bucket_folder, monkeypatch, storage_registry
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket, db_session=db_session)
    admin = UserFactory.build(email="admin@relic.local", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.commit()

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )

    result = object_writes.put_object(
        db_session,
        storage=storage_registry,
        bucket_name="photos",
        key="cat.jpg",
        body=b"cat",
        ingest_meta={},
        current_user=admin,
    )

    assert result.file.name == "cat.jpg"


def test_put_object_with_user_allows_inherited_write(
    db_session, bucket_folder, monkeypatch, storage_registry
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket, db_session=db_session)
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        FolderAccess(
            actor_id=user.id,
            folder_id=bucket_folder.id,
            permissions=int(Permission.READ | Permission.WRITE),
        )
    )
    db_session.commit()

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client", lambda **kwargs: FakeS3Client()
    )

    result = object_writes.put_object(
        db_session,
        storage=storage_registry,
        bucket_name="photos",
        key="2026/cat.jpg",
        body=b"cat",
        ingest_meta={},
        current_user=user,
    )

    assert result.file.name == "cat.jpg"
