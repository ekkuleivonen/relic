import io

import pytest
from enums import BucketTier
from models import AuditEvent, Base, Blob, MaintenanceEvent
from services.placement import clear_bucket_usage_cache, get_bucket_usage
from services.storage_maintenance import (
    probe_all_buckets,
    purge_dereferenced_blobs_batch,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
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


def test_purge_deletes_dereferenced_blob_and_adjusts_counters(db_session, fake_storage):
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
    assert db_session.scalars(select(AuditEvent)).all() == []
    events = db_session.scalars(select(MaintenanceEvent)).all()
    assert len(events) == 1
    assert events[0].job == "purge_dereferenced_blobs"
    assert events[0].action == "blob.purged"
    assert events[0].status == "succeeded"
    assert events[0].blob_id == blob_row.id
    assert events[0].meta["freed_bytes"] == 100


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
    assert db_session.scalars(select(AuditEvent)).all() == []
    assert db_session.scalars(select(MaintenanceEvent)).all() == []


def test_successful_scheduled_probe_emits_maintenance_event_not_audit_event(
    db_session, monkeypatch
):
    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

        def head_object(self, Bucket, Key):
            return None

        def get_object(self, Bucket, Key):
            class Body:
                def read(self):
                    return b"relic-probe"

            return {"Body": Body()}

        def delete_object(self, Bucket, Key):
            return None

    monkeypatch.setattr(
        "services.buckets.boto3.client",
        lambda *args, **kwargs: FakeS3Client(),
    )
    bucket_row = BucketFactory.build(tier=int(BucketTier.HOT))
    db_session.add(bucket_row)
    db_session.commit()

    result = probe_all_buckets(db_session)

    assert result == {"bucket_count": 1, "ok": 1, "failed": 0}
    assert db_session.scalars(select(AuditEvent)).all() == []
    events = db_session.scalars(select(MaintenanceEvent)).all()
    assert len(events) == 1
    assert events[0].job == "bucket_probe"
    assert events[0].action == "bucket.probe_ok"
    assert events[0].status == "succeeded"
    assert events[0].bucket_id == bucket_row.id
    assert events[0].meta == {
        "put_ms": bucket_row.probe_latency_put_ms,
        "head_ms": bucket_row.probe_latency_head_ms,
        "get_ms": bucket_row.probe_latency_get_ms,
        "delete_ms": bucket_row.probe_latency_delete_ms,
    }
