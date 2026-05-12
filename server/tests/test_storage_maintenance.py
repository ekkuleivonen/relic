import io

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, Blob
from schema_plan import BucketTier
from services.placement import clear_bucket_usage_cache, get_bucket_usage
from services.storage_maintenance import purge_dereferenced_blobs_batch
from tests.factories.models import BlobFactory, BucketFactory


class FakeStreamingBody:
    def __init__(self, data: bytes):
        self._buffer = io.BytesIO(data)

    def read(self, size=-1):
        return self._buffer.read(size)


class FakeBucketStore:
    """In-memory bucket; aligns with FakeBucketStore in test_file_gateway_ops."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def make_client(self):
        store = self

        class _Client:
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


def test_purge_deletes_dereferenced_blob_and_adjusts_counters(
    db_session, fake_storage
):
    bucket_row = BucketFactory.build(tier=int(BucketTier.HOT))
    db_session.add(bucket_row)
    db_session.flush()

    blob_row = BlobFactory.build(
        bucket_id=bucket_row.id,
        refcount=0,
        size_bytes=100,
        content_hash=b"\x02" * 32,
        bucket_key="objs/k1",
    )
    db_session.add(blob_row)
    db_session.commit()

    fake_storage.objects[(bucket_row.bucket, blob_row.bucket_key)] = b"payload"

    out = purge_dereferenced_blobs_batch(db_session, batch=50)
    assert out["deleted_rows"] == 1
    assert out["freed_bytes"] == 100
    assert out["errors"] == 0
    assert db_session.get(Blob, blob_row.id) is None

    usage = get_bucket_usage(db_session, bucket_row.id)
    assert usage.object_count == 0
    assert usage.current_size_bytes == 0
    assert fake_storage.objects == {}


def test_purge_skips_positive_refcount(db_session, fake_storage):
    bucket_row = BucketFactory.build(tier=int(BucketTier.HOT))
    db_session.add(bucket_row)
    db_session.flush()

    blob_row = BlobFactory.build(
        bucket_id=bucket_row.id,
        refcount=1,
        size_bytes=10,
        content_hash=b"\x03" * 32,
        bucket_key="objs/k-live",
    )
    db_session.add(blob_row)
    db_session.commit()

    fake_storage.objects[(bucket_row.bucket, blob_row.bucket_key)] = b"x"

    out = purge_dereferenced_blobs_batch(db_session, batch=50)
    assert out["deleted_rows"] == 0
    assert out["scanned"] == 0
    assert db_session.get(Blob, blob_row.id) is not None
    usage = get_bucket_usage(db_session, bucket_row.id)
    assert usage.object_count == 1
    assert usage.current_size_bytes == 10
