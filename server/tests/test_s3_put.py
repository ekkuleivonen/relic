import hashlib
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from managers.exceptions import ConflictError, ResourceNotFound
from models import Base, Blob, Bucket, File, Folder, FolderAccess
from schema_plan import ROOT_FOLDER_SCHEMA, BucketTier, Permission, UserRole
from services import objects as object_service
from services.placement import choose_bucket
from tests.factories.models import BlobFactory, BucketFactory, UserFactory


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


@pytest.fixture()
def root_folder(db_session):
    root = Folder(
        name="",
        parent_id=None,
        schema=ROOT_FOLDER_SCHEMA,
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
        schema=ROOT_FOLDER_SCHEMA,
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


def test_choose_bucket_filters_capacity_and_prefers_latency(db_session):
    full = add_bucket(
        db_session,
        name="full",
        max_size_bytes=10,
        current_size_bytes=9,
    )
    slow = add_bucket(db_session, name="slow")
    fast = add_bucket(db_session, name="fast")
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
        current_size_bytes=3,
    )
    mark_healthy(bucket)
    db_session.commit()

    with pytest.raises(ConflictError):
        choose_bucket(db_session, tier=BucketTier.HOT, size_bytes=1)


def test_put_object_uploads_new_blob_and_creates_file(
    client, db_session, bucket_folder, monkeypatch
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket)
    db_session.commit()
    body = b"cat photo"
    uploaded = []

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            uploaded.append({"Bucket": Bucket, "Key": Key, "Body": Body})

    monkeypatch.setattr("services.objects.boto3.client", lambda **kwargs: FakeS3Client())

    response = client.put(
        "/photos/2026/cat.jpg",
        content=body,
        headers={"content-type": "image/jpeg", "x-amz-meta-album": "spring"},
    )

    assert response.status_code == 200
    digest = hashlib.sha256(body).digest()
    digest_hex = digest.hex()
    assert response.headers["etag"] == f'"{digest_hex}"'
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
    db_session.refresh(physical_bucket)
    assert physical_bucket.object_count == 1
    assert physical_bucket.current_size_bytes == len(body)

    child_folder = db_session.scalar(
        select(Folder).where(Folder.parent_id == bucket_folder.id, Folder.name == "2026")
    )
    assert child_folder is not None
    file = db_session.scalar(select(File).where(File.folder_id == child_folder.id))
    assert file is not None
    assert file.name == "cat.jpg"
    assert file.blob_id == blob.id
    assert file.meta["file_size"] == len(body)
    assert file.meta["mime_type"] == "image/jpeg"
    assert file.meta["extension"] == ".jpg"
    assert file.meta["album"] == "spring"


def test_put_object_dedupes_existing_blob(client, db_session, bucket_folder, monkeypatch):
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

    response = client.put("/photos/copy.txt", content=body)

    assert response.status_code == 200
    db_session.refresh(blob)
    db_session.refresh(physical_bucket)
    assert blob.refcount == 2
    assert physical_bucket.object_count == 0
    assert physical_bucket.current_size_bytes == 0


def test_put_object_rejects_existing_file_name(
    client, db_session, root_folder, bucket_folder, monkeypatch
):
    physical_bucket = add_bucket(db_session, name="hot")
    mark_healthy(physical_bucket)
    blob = BlobFactory(bucket_id=physical_bucket.id)
    db_session.add(blob)
    db_session.flush()
    db_session.add(
        File(
            folder_id=bucket_folder.id,
            blob_id=blob.id,
            name="cat.jpg",
            meta={
                "original_name": "cat.jpg",
                "file_size": 1,
                "mime_type": "image/jpeg",
                "extension": ".jpg",
            },
        )
    )
    db_session.commit()

    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            raise AssertionError("conflicting file should not be uploaded")

    monkeypatch.setattr("services.objects.boto3.client", lambda **kwargs: FakeS3Client())

    response = client.put("/photos/cat.jpg", content=b"new")

    assert response.status_code == 409
    assert response.json()["detail"] == "File already exists"


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
            content_type="image/jpeg",
            user_metadata={},
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
        content_type="image/jpeg",
        user_metadata={},
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
        content_type="image/jpeg",
        user_metadata={},
        current_user=user,
    )

    assert result.file.name == "cat.jpg"
