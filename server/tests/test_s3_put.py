import hashlib
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from file_meta import build_file_meta
from managers.exceptions import ConflictError, ResourceNotFound
from models import (
    Base,
    Blob,
    Bucket,
    File,
    FileEvent,
    Folder,
    FolderAccess,
    META_EXTRACT_STATUS_PENDING,
)
from schema_plan import BucketTier, Permission, UserRole
from services import objects as object_service
from services.event_context import EventContext
from services.placement import choose_bucket, clear_bucket_usage_cache, get_bucket_usage
from tests.factories.models import BlobFactory, BucketFactory, UserFactory


@pytest.fixture()
def db_session():
    clear_bucket_usage_cache()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        yield session
    clear_bucket_usage_cache()


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
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(root)
    db_session.commit()
    return root


@pytest.fixture()
def bucket_folder(db_session, root_folder):
    folder = Folder(
        name="photos",
        parent_id=root_folder.id,
        cooldown_days=None,
        min_tier=BucketTier.HOT,
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


def mark_healthy(bucket: Bucket, latency: int = 10) -> None:
    bucket.probe_latency_put_ms = latency
    bucket.probe_latency_head_ms = latency
    bucket.probe_latency_get_ms = latency
    bucket.probe_latency_delete_ms = latency


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
    mark_healthy(full, 1)
    mark_healthy(slow, 50)
    mark_healthy(fast, 5)
    db_session.commit()

    chosen = choose_bucket(db_session, tier=BucketTier.HOT, size_bytes=2)

    assert chosen.id == fast.id


def test_choose_bucket_raises_when_no_bucket_has_capacity(db_session):
    bucket = add_bucket(
        db_session,
        name="tiny",
        max_size_bytes=3,
    )
    db_session.add(BlobFactory.build(bucket_id=bucket.id, size_bytes=3))
    mark_healthy(bucket)
    db_session.commit()

    with pytest.raises(ConflictError):
        choose_bucket(db_session, tier=BucketTier.HOT, size_bytes=1)


def test_put_object_uploads_new_blob_and_creates_file(
    db_session, bucket_folder, monkeypatch
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket)
    db_session.commit()
    body = b"cat photo"
    uploaded = []

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            Body = read_body(Body)
            uploaded.append({"Bucket": Bucket, "Key": Key, "Body": Body})

    monkeypatch.setattr("services.objects.boto3.client", lambda **kwargs: FakeS3Client())

    user = UserFactory.build(email="user@relic.local", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    result = object_service.put_object(
        db_session,
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
        select(Folder).where(Folder.parent_id == bucket_folder.id, Folder.name == "2026")
    )
    assert child_folder is not None
    file = db_session.scalar(select(File).where(File.folder_id == child_folder.id))
    assert file is not None
    assert file.name == "cat.jpg"
    assert file.blob_id == blob.id
    assert file.uploaded_by == user.id
    assert file.meta_extract_status == META_EXTRACT_STATUS_PENDING
    assert file.meta["kvs"]["album"] == "spring"
    assert file.meta["original_filename"] == "cat.jpg"


def test_put_object_resolves_min_tier_for_inherited_folder(
    db_session, root_folder, monkeypatch
):
    physical_cold = add_bucket(db_session, name="cold", tier=BucketTier.COLD)
    mark_healthy(physical_cold)
    bucket_folder = Folder(
        name="archive",
        parent_id=root_folder.id,
        cooldown_days=None,
        min_tier=int(BucketTier.COLD),
    )
    db_session.add(bucket_folder)
    db_session.commit()

    captured: list[BucketTier] = []

    def fake_choose(db, tier, size_bytes):
        captured.append(tier)
        return physical_cold

    monkeypatch.setattr("services.objects.choose_bucket", fake_choose)
    monkeypatch.setattr("services.objects.upload_blob", lambda **kwargs: None)

    user = UserFactory.build(email="user@relic.local", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()

    body = b"z"
    object_service.put_object(
        db_session,
        bucket_name="archive",
        key="2026/a.jpg",
        body=body,
        ingest_meta={},
        current_user=user,
    )

    assert captured == [BucketTier.COLD]


def test_put_object_dedupes_existing_blob(db_session, bucket_folder, monkeypatch):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket)
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

    monkeypatch.setattr("services.objects.boto3.client", lambda **kwargs: FakeS3Client())

    user = UserFactory.build(email="user@relic.local", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    result = object_service.put_object(
        db_session,
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
    db_session, root_folder, bucket_folder, monkeypatch
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket)
    old_blob = BlobFactory(bucket_id=physical_bucket.id, refcount=1)
    owner = UserFactory.build(email="owner@relic.local", role=UserRole.ADMIN)
    db_session.add(owner)
    db_session.add(old_blob)
    db_session.flush()
    existing_file = File(
        folder_id=bucket_folder.id,
        blob_id=old_blob.id,
        uploaded_by=owner.id,
        name="cat.jpg",
        meta=build_file_meta(
            file_name="cat.jpg", size=old_blob.size_bytes, user_meta={}
        ),
    )
    db_session.add(existing_file)
    db_session.commit()
    body = b"new"
    uploaded = []

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            uploaded.append({"Bucket": Bucket, "Key": Key, "Body": read_body(Body)})

    monkeypatch.setattr("services.objects.boto3.client", lambda **kwargs: FakeS3Client())

    result = object_service.put_object(
        db_session,
        bucket_name="photos",
        key="cat.jpg",
        body=body,
        ingest_meta={"album": "summer"},
        current_user=owner,
        event_context=EventContext(actor_user_id=owner.id, request_id="req-update"),
    )

    assert len(uploaded) == 1
    assert result.file.id == existing_file.id
    assert result.file.blob_id != old_blob.id
    assert result.file.meta["kvs"]["album"] == "summer"
    db_session.refresh(old_blob)
    assert old_blob.refcount == 0
    updated_event = db_session.scalars(
        select(FileEvent).where(FileEvent.event_type == "file.updated")
    ).one()
    assert updated_event.file_id == existing_file.id
    assert updated_event.payload["previous_blob_id"] == str(old_blob.id)
    assert updated_event.payload["blob_id"] == str(result.blob.id)


def test_put_object_with_user_requires_write_permission(db_session, bucket_folder):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()

    with pytest.raises(ResourceNotFound):
        object_service.put_object(
            db_session,
            bucket_name="photos",
            key="cat.jpg",
            body=b"cat",
            ingest_meta={},
            current_user=user,
        )


def test_put_object_with_admin_user_bypasses_folder_access(
    db_session, bucket_folder, monkeypatch
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket)
    admin = UserFactory.build(email="admin@relic.local", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.commit()

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

    monkeypatch.setattr("services.objects.boto3.client", lambda **kwargs: FakeS3Client())

    result = object_service.put_object(
        db_session,
        bucket_name="photos",
        key="cat.jpg",
        body=b"cat",
        ingest_meta={},
        current_user=admin,
    )

    assert result.file.name == "cat.jpg"


def test_put_object_with_user_allows_inherited_write(
    db_session, bucket_folder, monkeypatch
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket)
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        FolderAccess(
            user_id=user.id,
            folder_id=bucket_folder.id,
            permissions=int(Permission.READ | Permission.WRITE),
        )
    )
    db_session.commit()

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

    monkeypatch.setattr("services.objects.boto3.client", lambda **kwargs: FakeS3Client())

    result = object_service.put_object(
        db_session,
        bucket_name="photos",
        key="2026/cat.jpg",
        body=b"cat",
        ingest_meta={},
        current_user=user,
    )

    assert result.file.name == "cat.jpg"
