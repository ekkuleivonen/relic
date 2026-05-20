import datetime as dt
import io

import pytest
from models import AuditEvent, Base, Blob, BucketProbe
from services.placement import clear_bucket_usage_cache, get_bucket_usage
from services.storage_maintenance import (
    demote_pressured_buckets_batch,
    probe_all_buckets,
    promote_recently_accessed_batch,
    purge_dereferenced_blobs_batch,
    trim_old_bucket_probes_batch,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import (
    BlobFactory,
    BucketFactory,
    BucketProbeFactory,
)


class FakeStreamingBody:
    def __init__(self, data: bytes):
        self._buffer = io.BytesIO(data)

    def read(self, size=-1):
        return self._buffer.read(size)


class FakeBucketStore:
    """In-memory backing store for object copy/delete during migration tests."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def make_client(self):
        store = self

        class _Client:
            def get_object(self, Bucket, Key, Range=None):
                data = store.objects[(Bucket, Key)]
                return {"Body": FakeStreamingBody(data), "ContentLength": len(data)}

            def put_object(self, Bucket, Key, Body):
                if hasattr(Body, "read"):
                    Body.seek(0)
                    Body = Body.read()
                store.objects[(Bucket, Key)] = Body

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


def add_probe(db_session, bucket, *, latency: int = 10, success: bool = True) -> None:
    db_session.add(
        BucketProbeFactory.build(
            bucket_id=bucket.id,
            success=success,
            put_ms=latency,
            head_ms=latency,
            get_ms=latency,
            delete_ms=latency,
        )
    )


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------


def test_purge_deletes_dereferenced_blob_and_adjusts_counters(
    db_session, fake_storage
):
    bucket_row = BucketFactory.build()
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
    events = db_session.scalars(select(AuditEvent)).all()
    assert len(events) == 1
    assert events[0].job == "purge_dereferenced_blobs"
    assert events[0].operation == "blob.purged"
    assert events[0].status == "succeeded"
    assert events[0].blob_id == blob_row.id
    assert events[0].meta["freed_bytes"] == 100


def test_purge_skips_positive_refcount(db_session, fake_storage):
    bucket_row = BucketFactory.build()
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


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


def test_successful_scheduled_probe_records_probe_without_maintenance_event(
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
    bucket_row = BucketFactory.build()
    db_session.add(bucket_row)
    db_session.commit()

    result = probe_all_buckets(db_session)

    assert result == {"bucket_count": 1, "ok": 1, "failed": 0}
    assert db_session.scalars(select(AuditEvent)).all() == []
    sample = db_session.scalar(
        select(BucketProbe).where(BucketProbe.bucket_id == bucket_row.id)
    )
    assert sample is not None
    assert sample.success is True


def test_trim_old_bucket_probes_drops_only_records_past_retention(db_session):
    bucket = BucketFactory.build()
    db_session.add(bucket)
    db_session.flush()

    fresh = BucketProbeFactory.build(bucket_id=bucket.id)
    stale = BucketProbeFactory.build(
        bucket_id=bucket.id,
        observed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=10),
    )
    db_session.add_all([fresh, stale])
    db_session.commit()

    out = trim_old_bucket_probes_batch(db_session, retention_days=7)

    assert out["deleted_rows"] == 1
    remaining = db_session.scalars(
        select(BucketProbe).where(BucketProbe.bucket_id == bucket.id)
    ).all()
    assert [r.id for r in remaining] == [fresh.id]
    events = db_session.scalars(select(AuditEvent)).all()
    assert len(events) == 1
    assert events[0].job == "trim_bucket_probes"
    assert events[0].operation == "bucket_probe.trimmed"
    assert events[0].meta == {"retention_days": 7, "deleted_rows": 1}


def test_trim_old_bucket_probes_skips_event_when_nothing_deleted(db_session):
    bucket = BucketFactory.build()
    db_session.add(bucket)
    db_session.flush()

    fresh = BucketProbeFactory.build(bucket_id=bucket.id)
    db_session.add(fresh)
    db_session.commit()

    out = trim_old_bucket_probes_batch(db_session, retention_days=7)

    assert out["deleted_rows"] == 0
    assert db_session.scalars(select(BucketProbe)).all() == [fresh]
    assert db_session.scalars(select(AuditEvent)).all() == []


# ---------------------------------------------------------------------------
# Demote
# ---------------------------------------------------------------------------


def test_demote_moves_oldest_blob_when_bucket_is_pressured(db_session, fake_storage):
    hot = BucketFactory.build(name="hot", bucket="hot-blobs", max_size_bytes=100)
    cold = BucketFactory.build(name="cold", bucket="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()

    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    cold_blob = BlobFactory.build(
        bucket_id=hot.id,
        refcount=1,
        size_bytes=80,
        content_hash=b"\x10" * 32,
        bucket_key="objs/cold",
        accessed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=30),
    )
    db_session.add(cold_blob)
    db_session.commit()

    fake_storage.objects[(hot.bucket, cold_blob.bucket_key)] = b"x" * 80

    out = demote_pressured_buckets_batch(
        db_session,
        demote_limit=5,
        pressure_ratio=0.5,
        headroom_ratio=0.9,
        min_residency_hours=0,
    )

    assert out["moved"] == 1
    db_session.refresh(cold_blob)
    assert cold_blob.bucket_id == cold.id
    assert cold_blob.migrated_at is not None
    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.job == "demote_pressured_buckets")
    ).all()
    assert any(e.operation == "blob.demoted" for e in events)
    assert (cold.bucket, cold_blob.bucket_key) in fake_storage.objects
    assert (hot.bucket, cold_blob.bucket_key) not in fake_storage.objects


def test_demote_does_nothing_when_no_bucket_is_pressured(db_session, fake_storage):
    hot = BucketFactory.build(name="hot", bucket="hot-blobs", max_size_bytes=1_000)
    cold = BucketFactory.build(name="cold", bucket="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    blob = BlobFactory.build(
        bucket_id=hot.id, refcount=1, size_bytes=10, content_hash=b"\x20" * 32
    )
    db_session.add(blob)
    db_session.commit()

    out = demote_pressured_buckets_batch(
        db_session,
        demote_limit=5,
        pressure_ratio=0.85,
        headroom_ratio=0.9,
        min_residency_hours=0,
    )

    assert out == {"scanned": 0, "moved": 0, "skipped": 0, "failed": 0}
    db_session.refresh(blob)
    assert blob.bucket_id == hot.id


def test_demote_respects_min_residency(db_session, fake_storage):
    hot = BucketFactory.build(name="hot", bucket="hot-blobs", max_size_bytes=100)
    cold = BucketFactory.build(name="cold", bucket="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    blob = BlobFactory.build(
        bucket_id=hot.id,
        refcount=1,
        size_bytes=80,
        content_hash=b"\x21" * 32,
        bucket_key="objs/recent",
        accessed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=30),
        migrated_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(blob)
    db_session.commit()
    fake_storage.objects[(hot.bucket, blob.bucket_key)] = b"x" * 80

    out = demote_pressured_buckets_batch(
        db_session,
        demote_limit=5,
        pressure_ratio=0.5,
        headroom_ratio=0.9,
        min_residency_hours=12,
    )

    assert out["moved"] == 0
    db_session.refresh(blob)
    assert blob.bucket_id == hot.id


# ---------------------------------------------------------------------------
# Promote
# ---------------------------------------------------------------------------


def test_promote_moves_recent_blob_to_hotter_bucket(db_session, fake_storage):
    hot = BucketFactory.build(name="hot", bucket="hot-blobs", max_size_bytes=1_000)
    cold = BucketFactory.build(name="cold", bucket="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    blob = BlobFactory.build(
        bucket_id=cold.id,
        refcount=1,
        size_bytes=10,
        content_hash=b"\x30" * 32,
        bucket_key="objs/promote",
        accessed_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(blob)
    db_session.commit()
    fake_storage.objects[(cold.bucket, blob.bucket_key)] = b"y" * 10

    out = promote_recently_accessed_batch(
        db_session,
        promote_limit=5,
        headroom_ratio=0.9,
        recency_days=7,
        min_residency_hours=0,
    )

    assert out["moved"] == 1
    db_session.refresh(blob)
    assert blob.bucket_id == hot.id
    assert blob.migrated_at is not None
    assert (hot.bucket, blob.bucket_key) in fake_storage.objects
    assert (cold.bucket, blob.bucket_key) not in fake_storage.objects
    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.job == "promote_recently_accessed"
        )
    ).all()
    assert any(e.operation == "blob.promoted" for e in events)


def test_promote_skips_blob_outside_recency_window(db_session, fake_storage):
    hot = BucketFactory.build(name="hot", bucket="hot-blobs", max_size_bytes=1_000)
    cold = BucketFactory.build(name="cold", bucket="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    blob = BlobFactory.build(
        bucket_id=cold.id,
        refcount=1,
        size_bytes=10,
        content_hash=b"\x31" * 32,
        bucket_key="objs/stale",
        accessed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=30),
    )
    db_session.add(blob)
    db_session.commit()

    out = promote_recently_accessed_batch(
        db_session,
        promote_limit=5,
        headroom_ratio=0.9,
        recency_days=7,
        min_residency_hours=0,
    )

    assert out["moved"] == 0
    db_session.refresh(blob)
    assert blob.bucket_id == cold.id


def test_promote_skips_when_hotter_bucket_lacks_headroom(db_session, fake_storage):
    hot = BucketFactory.build(name="hot", bucket="hot-blobs", max_size_bytes=10)
    cold = BucketFactory.build(name="cold", bucket="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    db_session.add(
        BlobFactory.build(
            bucket_id=hot.id, refcount=1, size_bytes=10, content_hash=b"\xa0" * 32
        )
    )
    blob = BlobFactory.build(
        bucket_id=cold.id,
        refcount=1,
        size_bytes=10,
        content_hash=b"\xa1" * 32,
        bucket_key="objs/no-headroom",
        accessed_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(blob)
    db_session.commit()

    out = promote_recently_accessed_batch(
        db_session,
        promote_limit=5,
        headroom_ratio=0.9,
        recency_days=7,
        min_residency_hours=0,
    )

    assert out["moved"] == 0
    db_session.refresh(blob)
    assert blob.bucket_id == cold.id
