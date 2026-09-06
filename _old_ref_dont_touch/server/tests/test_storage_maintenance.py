import datetime as dt
import io

import pytest
from infra.db.models import AuditEvent, Base, Blob, StorageBackendProbe
from infra.db.stores.placement import clear_storage_backend_usage_cache, get_storage_backend_usage
from infra.maintenance.storage import (
    demote_pressured_storage_backends_batch,
    probe_all_storage_backends,
    promote_recently_accessed_batch,
    purge_dereferenced_blobs_batch,
    trim_old_storage_backend_probes_batch,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import (
    BlobFactory,
    StorageBackendFactory,
    StorageBackendProbeFactory,
)


class FakeStreamingBody:
    def __init__(self, data: bytes):
        self._buffer = io.BytesIO(data)

    def read(self, size=-1):
        return self._buffer.read(size)


class FakeStorageBackendStore:
    """In-memory backing store for object copy/delete during migration tests."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def make_client(self):
        store = self

        class _Client:
            def head_object(self, Bucket, Key):
                data = store.objects[(Bucket, Key)]
                return {"ContentLength": len(data)}

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
    store = FakeStorageBackendStore()
    monkeypatch.setattr(
        "infra.object_storage.registry.boto3.client",
        lambda **kwargs: store.make_client(),
    )
    return store


def add_probe(db_session, bucket, *, latency: int = 10, success: bool = True) -> None:
    db_session.add(
        StorageBackendProbeFactory.build(
            storage_backend_id=bucket.id,
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
    db_session, fake_storage, run_uow
):
    bucket_row = StorageBackendFactory.build()
    db_session.add(bucket_row)
    db_session.flush()

    blob_row = BlobFactory.build(
        storage_backend_id=bucket_row.id,
        refcount=0,
        size_bytes=100,
        content_hash=b"\x02" * 32,
        bucket_key="objs/k1",
    )
    db_session.add(blob_row)
    db_session.commit()

    fake_storage.objects[(bucket_row.namespace, blob_row.bucket_key)] = b"payload"

    out = run_uow(lambda uow: purge_dereferenced_blobs_batch(uow, batch=50))
    assert out["deleted_rows"] == 1
    assert out["freed_bytes"] == 100
    assert out["errors"] == 0
    assert db_session.get(Blob, blob_row.id) is None

    usage = get_storage_backend_usage(db_session, bucket_row.id)
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


def test_purge_skips_positive_refcount(db_session, fake_storage, run_uow):
    bucket_row = StorageBackendFactory.build()
    db_session.add(bucket_row)
    db_session.flush()

    blob_row = BlobFactory.build(
        storage_backend_id=bucket_row.id,
        refcount=1,
        size_bytes=10,
        content_hash=b"\x03" * 32,
        bucket_key="objs/k-live",
    )
    db_session.add(blob_row)
    db_session.commit()

    fake_storage.objects[(bucket_row.namespace, blob_row.bucket_key)] = b"x"

    out = run_uow(lambda uow: purge_dereferenced_blobs_batch(uow, batch=50))
    assert out["deleted_rows"] == 0
    assert out["scanned"] == 0
    assert db_session.get(Blob, blob_row.id) is not None
    usage = get_storage_backend_usage(db_session, bucket_row.id)
    assert usage.object_count == 1
    assert usage.current_size_bytes == 10
    assert db_session.scalars(select(AuditEvent)).all() == []


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


def test_successful_scheduled_probe_records_probe_without_maintenance_event(
    db_session, monkeypatch, run_uow
):
    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

        def head_object(self, Bucket, Key):
            return None

        def get_object(self, Bucket, Key):
            class Body:
                def read(self):
                    return b"pithosys-probe"

            return {"Body": Body()}

        def delete_object(self, Bucket, Key):
            return None

    monkeypatch.setattr(
        "infra.db.stores.storage_backend_probe.boto3.client",
        lambda *args, **kwargs: FakeS3Client(),
    )
    bucket_row = StorageBackendFactory.build()
    db_session.add(bucket_row)
    db_session.commit()

    result = run_uow(lambda uow: probe_all_storage_backends(uow))

    assert result == {"bucket_count": 1, "ok": 1, "failed": 0}
    assert db_session.scalars(select(AuditEvent)).all() == []
    sample = db_session.scalar(
        select(StorageBackendProbe).where(StorageBackendProbe.storage_backend_id == bucket_row.id)
    )
    assert sample is not None
    assert sample.success is True


def test_trim_old_storage_backend_probes_drops_only_records_past_retention(db_session, run_uow):
    bucket = StorageBackendFactory.build()
    db_session.add(bucket)
    db_session.flush()

    fresh = StorageBackendProbeFactory.build(storage_backend_id=bucket.id)
    stale = StorageBackendProbeFactory.build(
        storage_backend_id=bucket.id,
        observed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=10),
    )
    db_session.add_all([fresh, stale])
    db_session.commit()

    out = run_uow(lambda uow: trim_old_storage_backend_probes_batch(uow, retention_days=7))

    assert out["deleted_rows"] == 1
    remaining = db_session.scalars(
        select(StorageBackendProbe).where(StorageBackendProbe.storage_backend_id == bucket.id)
    ).all()
    assert [r.id for r in remaining] == [fresh.id]
    events = db_session.scalars(select(AuditEvent)).all()
    assert len(events) == 1
    assert events[0].job == "trim_storage_backend_probes"
    assert events[0].operation == "storage_backend_probe.trimmed"
    assert events[0].meta == {"retention_days": 7, "deleted_rows": 1}


def test_trim_old_storage_backend_probes_skips_event_when_nothing_deleted(db_session, run_uow):
    bucket = StorageBackendFactory.build()
    db_session.add(bucket)
    db_session.flush()

    fresh = StorageBackendProbeFactory.build(storage_backend_id=bucket.id)
    db_session.add(fresh)
    db_session.commit()

    out = run_uow(lambda uow: trim_old_storage_backend_probes_batch(uow, retention_days=7))

    assert out["deleted_rows"] == 0
    assert db_session.scalars(select(StorageBackendProbe)).all() == [fresh]
    assert db_session.scalars(select(AuditEvent)).all() == []


# ---------------------------------------------------------------------------
# Demote
# ---------------------------------------------------------------------------


def test_demote_moves_oldest_blob_when_bucket_is_pressured(db_session, fake_storage, run_uow):
    hot = StorageBackendFactory.build(name="hot", namespace="hot-blobs", max_size_bytes=100)
    cold = StorageBackendFactory.build(name="cold", namespace="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()

    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    cold_blob = BlobFactory.build(
        storage_backend_id=hot.id,
        refcount=1,
        size_bytes=80,
        content_hash=b"\x10" * 32,
        bucket_key="objs/cold",
        accessed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=30),
    )
    db_session.add(cold_blob)
    db_session.commit()

    fake_storage.objects[(hot.namespace, cold_blob.bucket_key)] = b"x" * 80

    out = run_uow(
        lambda uow: demote_pressured_storage_backends_batch(
            uow,
            demote_limit=5,
            pressure_ratio=0.5,
            headroom_ratio=0.9,
            min_residency_hours=0,
        )
    )

    assert out["moved"] == 1
    db_session.refresh(cold_blob)
    assert cold_blob.storage_backend_id == cold.id
    assert cold_blob.migrated_at is not None
    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.job == "demote_pressured_buckets")
    ).all()
    assert any(e.operation == "blob.demoted" for e in events)
    assert (cold.namespace, cold_blob.bucket_key) in fake_storage.objects
    assert (hot.namespace, cold_blob.bucket_key) not in fake_storage.objects


def test_demote_does_nothing_when_no_bucket_is_pressured(db_session, fake_storage, run_uow):
    hot = StorageBackendFactory.build(name="hot", namespace="hot-blobs", max_size_bytes=1_000)
    cold = StorageBackendFactory.build(name="cold", namespace="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    blob = BlobFactory.build(
        storage_backend_id=hot.id, refcount=1, size_bytes=10, content_hash=b"\x20" * 32
    )
    db_session.add(blob)
    db_session.commit()

    out = run_uow(
        lambda uow: demote_pressured_storage_backends_batch(
            uow,
            demote_limit=5,
            pressure_ratio=0.85,
            headroom_ratio=0.9,
            min_residency_hours=0,
        )
    )

    assert out == {"scanned": 0, "moved": 0, "skipped": 0, "failed": 0}
    db_session.refresh(blob)
    assert blob.storage_backend_id == hot.id


def test_demote_respects_min_residency(db_session, fake_storage, run_uow):
    hot = StorageBackendFactory.build(name="hot", namespace="hot-blobs", max_size_bytes=100)
    cold = StorageBackendFactory.build(name="cold", namespace="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    blob = BlobFactory.build(
        storage_backend_id=hot.id,
        refcount=1,
        size_bytes=80,
        content_hash=b"\x21" * 32,
        bucket_key="objs/recent",
        accessed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=30),
        migrated_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(blob)
    db_session.commit()
    fake_storage.objects[(hot.namespace, blob.bucket_key)] = b"x" * 80

    out = run_uow(
        lambda uow: demote_pressured_storage_backends_batch(
            uow,
            demote_limit=5,
            pressure_ratio=0.5,
            headroom_ratio=0.9,
            min_residency_hours=12,
        )
    )

    assert out["moved"] == 0
    db_session.refresh(blob)
    assert blob.storage_backend_id == hot.id


# ---------------------------------------------------------------------------
# Promote
# ---------------------------------------------------------------------------


def test_promote_moves_recent_blob_to_hotter_bucket(db_session, fake_storage, run_uow):
    hot = StorageBackendFactory.build(name="hot", namespace="hot-blobs", max_size_bytes=1_000)
    cold = StorageBackendFactory.build(name="cold", namespace="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    blob = BlobFactory.build(
        storage_backend_id=cold.id,
        refcount=1,
        size_bytes=10,
        content_hash=b"\x30" * 32,
        bucket_key="objs/promote",
        accessed_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(blob)
    db_session.commit()
    fake_storage.objects[(cold.namespace, blob.bucket_key)] = b"y" * 10

    out = run_uow(
        lambda uow: promote_recently_accessed_batch(
            uow,
            promote_limit=5,
            headroom_ratio=0.9,
            recency_days=7,
            min_residency_hours=0,
        )
    )

    assert out["moved"] == 1
    db_session.refresh(blob)
    assert blob.storage_backend_id == hot.id
    assert blob.migrated_at is not None
    assert (hot.namespace, blob.bucket_key) in fake_storage.objects
    assert (cold.namespace, blob.bucket_key) not in fake_storage.objects
    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.job == "promote_recently_accessed"
        )
    ).all()
    assert any(e.operation == "blob.promoted" for e in events)


def test_promote_skips_blob_outside_recency_window(db_session, fake_storage, run_uow):
    hot = StorageBackendFactory.build(name="hot", namespace="hot-blobs", max_size_bytes=1_000)
    cold = StorageBackendFactory.build(name="cold", namespace="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    blob = BlobFactory.build(
        storage_backend_id=cold.id,
        refcount=1,
        size_bytes=10,
        content_hash=b"\x31" * 32,
        bucket_key="objs/stale",
        accessed_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=30),
    )
    db_session.add(blob)
    db_session.commit()

    out = run_uow(
        lambda uow: promote_recently_accessed_batch(
            uow,
            promote_limit=5,
            headroom_ratio=0.9,
            recency_days=7,
            min_residency_hours=0,
        )
    )

    assert out["moved"] == 0
    db_session.refresh(blob)
    assert blob.storage_backend_id == cold.id


def test_promote_skips_when_hotter_bucket_lacks_headroom(db_session, fake_storage, run_uow):
    hot = StorageBackendFactory.build(name="hot", namespace="hot-blobs", max_size_bytes=10)
    cold = StorageBackendFactory.build(name="cold", namespace="cold-blobs", max_size_bytes=1_000)
    db_session.add_all([hot, cold])
    db_session.flush()
    add_probe(db_session, hot, latency=1)
    add_probe(db_session, cold, latency=100)

    db_session.add(
        BlobFactory.build(
            storage_backend_id=hot.id, refcount=1, size_bytes=10, content_hash=b"\xa0" * 32
        )
    )
    blob = BlobFactory.build(
        storage_backend_id=cold.id,
        refcount=1,
        size_bytes=10,
        content_hash=b"\xa1" * 32,
        bucket_key="objs/no-headroom",
        accessed_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(blob)
    db_session.commit()

    out = run_uow(
        lambda uow: promote_recently_accessed_batch(
            uow,
            promote_limit=5,
            headroom_ratio=0.9,
            recency_days=7,
            min_residency_hours=0,
        )
    )

    assert out["moved"] == 0
    db_session.refresh(blob)
    assert blob.storage_backend_id == cold.id
