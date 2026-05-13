"""Background blob lifecycle.

The cron has four independent jobs (see ``processors/worker_maintenance.py``):

* ``purge_dereferenced_blobs_batch`` — drop refcount=0 blob rows + remote bytes
* ``probe_all_buckets`` — write a fresh ``BucketProbe`` row for every bucket
* ``demote_pressured_buckets_batch`` — when a bucket reaches the demotion
  pressure ratio, push oldest-by-accessed_at blobs to the next-hottest bucket
  with capacity (latency-driven hotness ranking).
* ``promote_recently_accessed_batch`` — bubble up blobs whose ``accessed_at``
  is within the recency window into the hottest bucket that still has
  promotion headroom.
* ``trim_old_bucket_probes_batch`` — drop ``BucketProbe`` rows older than
  ``PROBES_RETENTION_DAYS`` so the table stays small.

Hysteresis: ``STORAGE_PROMOTION_HEADROOM_RATIO`` < ``STORAGE_DEMOTION_PRESSURE_RATIO``
plus a per-blob ``STORAGE_MIGRATION_MIN_RESIDENCY_HOURS`` cooloff prevents
the same blob from ping-ponging between buckets across consecutive ticks.

The migration helper writes the DB transition (`Blob.bucket_id`,
`migrated_at`) BEFORE deleting the source bytes, so a crash between upload
and src-delete leaves a recoverable orphan in the source bucket rather than
a missing blob row.
"""

import datetime as dt
import io
import uuid
from dataclasses import dataclass
from typing import Any

import settings as S
from botocore.exceptions import BotoCoreError, ClientError
from models import Blob, Bucket, BucketProbe, File
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload
from utils.logging import get_logger

from services import buckets as bucket_service
from services.audit_events import (
    elapsed_ms,
    timer_start,
)
from services.maintenance_events import create_maintenance_event
from services.objects import delete_blob_bytes, fetch_blob_bytes, upload_blob
from services.placement import (
    BucketHotness,
    adjust_bucket_usage_cache,
    agreed_preferred_bucket_id,
    get_bucket_usages,
    hotness_ranked_buckets,
)

log = get_logger(__name__)


@dataclass(frozen=True)
class BlobMigrationResult:
    migrated: bool
    status: str = "skipped"
    reason: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    db_latency_ms: int = 0
    remote_latency_ms: int = 0


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------


def purge_dereferenced_blobs_batch(
    db: Session,
    *,
    batch: int,
    batch_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """For blobs with refcount < 1, delete remote keys and Blob rows."""
    effective_batch_id = batch_id or uuid.uuid4()
    db_latency_ms = 0
    remote_latency_ms = 0
    dialect = db.get_bind().dialect.name
    stmt = (
        select(Blob)
        .where(Blob.refcount < 1)
        .order_by(Blob.updated_at.asc(), Blob.created_at.asc())
        .limit(batch)
    )
    if dialect in ("postgresql", "sqlite"):
        stmt = stmt.with_for_update(skip_locked=True)
    db_started = timer_start()
    blobs = list(db.scalars(stmt))
    db_latency_ms += elapsed_ms(db_started, minimum=0)

    deleted_rows = 0
    freed_bytes = 0
    errors = 0
    for blob in blobs:
        started_at = timer_start()
        bucket_id = blob.bucket_id
        blob_id = blob.id
        size_bytes = int(blob.size_bytes)
        bucket_key = blob.bucket_key
        try:
            with db.begin_nested():
                db_started = timer_start()
                bucket = db.get(Bucket, bucket_id)
                db_latency_ms += elapsed_ms(db_started, minimum=0)
                if bucket is not None:
                    try:
                        remote_started = timer_start()
                        delete_blob_bytes(bucket=bucket, bucket_key=blob.bucket_key)
                        remote_latency_ms += elapsed_ms(remote_started, minimum=0)
                    except (BotoCoreError, ClientError, OSError, ValueError) as exc:
                        log.warning(
                            "blob_purge_remote_delete_failed",
                            blob_id=str(blob.id),
                            bucket_id=str(blob.bucket_id),
                            error=str(exc),
                        )
                        raise
                    db_started = timer_start()
                    adjust_bucket_usage_cache(
                        bucket.id,
                        object_count_delta=-1,
                        size_bytes_delta=-blob.size_bytes,
                    )
                freed_bytes += size_bytes
                deleted_rows += 1
                db.delete(blob)
                db_latency_ms += elapsed_ms(db_started, minimum=0)
            create_maintenance_event(
                db,
                job="purge_dereferenced_blobs",
                action="blob.purged",
                status="succeeded",
                batch_id=effective_batch_id,
                bucket_id=bucket_id,
                blob_id=blob_id,
                duration_ms=elapsed_ms(started_at, minimum=0),
                metadata={
                    "freed_bytes": size_bytes,
                    "bucket_key": bucket_key,
                },
            )
        except Exception as exc:
            errors += 1
            create_maintenance_event(
                db,
                job="purge_dereferenced_blobs",
                action="blob.purge_failed",
                status="failed",
                batch_id=effective_batch_id,
                bucket_id=bucket_id,
                blob_id=blob_id,
                duration_ms=elapsed_ms(started_at, minimum=0),
                metadata={
                    "bucket_key": bucket_key,
                    "size_bytes": size_bytes,
                    "error_class": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )

    db.commit()

    log.info(
        "blob_purge_batch",
        scanned=len(blobs),
        deleted_rows=deleted_rows,
        freed_bytes=freed_bytes,
        errors=errors,
    )
    return {
        "scanned": len(blobs),
        "deleted_rows": deleted_rows,
        "freed_bytes": freed_bytes,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


def probe_all_buckets(
    db: Session,
    *,
    batch_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    effective_batch_id = batch_id or uuid.uuid4()
    buckets = bucket_service.list_buckets(db)
    ok = 0
    failed = 0
    for b in buckets:
        started_at = timer_start()
        try:
            result = bucket_service.probe_bucket(db, b.id)
            probe = result.probe
            metadata = {
                "put_ms": probe.put_ms,
                "head_ms": probe.head_ms,
                "get_ms": probe.get_ms,
                "delete_ms": probe.delete_ms,
            }
            if result.reachable:
                ok += 1
            else:
                failed += 1
                create_maintenance_event(
                    db,
                    job="bucket_probe",
                    action="bucket.probe_failed",
                    status="failed",
                    batch_id=effective_batch_id,
                    bucket_id=result.bucket.id,
                    duration_ms=elapsed_ms(started_at, minimum=0),
                    metadata=metadata,
                )
        except Exception as exc:
            failed += 1
            create_maintenance_event(
                db,
                job="bucket_probe",
                action="bucket.probe_failed",
                status="failed",
                batch_id=effective_batch_id,
                bucket_id=b.id,
                duration_ms=elapsed_ms(started_at, minimum=0),
                metadata={
                    "error_class": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            log.warning(
                "bucket_probe_failed_in_batch",
                bucket_id=str(b.id),
                error=str(exc),
            )
    db.commit()
    return {"bucket_count": len(buckets), "ok": ok, "failed": failed}


def trim_old_bucket_probes_batch(
    db: Session,
    *,
    retention_days: int,
    batch_id: uuid.UUID | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    effective_batch_id = batch_id or uuid.uuid4()
    effective_now = now or dt.datetime.now(dt.UTC)
    cutoff = effective_now - dt.timedelta(days=retention_days)

    started_at = timer_start()
    result = db.execute(
        delete(BucketProbe).where(BucketProbe.observed_at < cutoff)
    )
    deleted_rows = result.rowcount or 0
    if deleted_rows > 0:
        create_maintenance_event(
            db,
            job="trim_bucket_probes",
            action="bucket_probe.trimmed",
            status="succeeded",
            batch_id=effective_batch_id,
            duration_ms=elapsed_ms(started_at, minimum=0),
            metadata={
                "retention_days": retention_days,
                "deleted_rows": deleted_rows,
            },
        )
    db.commit()
    log.info(
        "bucket_probe_retention_trimmed",
        retention_days=retention_days,
        deleted_rows=deleted_rows,
    )
    return {"deleted_rows": deleted_rows}


# ---------------------------------------------------------------------------
# Migration helper (crash-safe ordering)
# ---------------------------------------------------------------------------


def _migrate_blob_to_bucket_inner(
    db: Session,
    blob: Blob,
    destination: Bucket,
    *,
    headroom_ratio: float | None = None,
) -> BlobMigrationResult:
    """Move a blob's bytes from its current bucket to ``destination``.

    Order of operations is crash-safety motivated:
        1. fetch source bytes
        2. upload to destination (may overwrite a prior partial copy)
        3. COMMIT the DB row (Blob.bucket_id, migrated_at)
        4. best-effort delete of the source bytes

    A crash between (3) and (4) leaves an orphan in the source bucket; the
    DB still resolves the blob to the destination, so reads are uninterrupted.
    Garbage collection of those orphans is acceptable cost vs. a missing blob.
    """
    if destination.id == blob.bucket_id:
        return BlobMigrationResult(migrated=False, reason="same_bucket")

    db_latency_ms = 0
    remote_latency_ms = 0
    db_started = timer_start()
    src = db.get(Bucket, blob.bucket_id)
    if src is None:
        return BlobMigrationResult(
            migrated=False,
            reason="source_bucket_missing",
            db_latency_ms=elapsed_ms(db_started, minimum=0),
        )

    destination_usage = get_bucket_usages(db, [destination.id])[destination.id]
    projected = destination_usage.current_size_bytes + blob.size_bytes
    if projected > destination.max_size_bytes:
        log.warning(
            "blob_migrate_destination_full",
            blob_id=str(blob.id),
            dest_bucket=str(destination.id),
        )
        return BlobMigrationResult(
            migrated=False,
            reason="destination_full",
            db_latency_ms=elapsed_ms(db_started, minimum=0),
        )
    if (
        headroom_ratio is not None
        and headroom_ratio < 1.0
        and projected > int(destination.max_size_bytes * headroom_ratio)
    ):
        return BlobMigrationResult(
            migrated=False,
            reason="destination_headroom_exceeded",
            db_latency_ms=elapsed_ms(db_started, minimum=0),
        )
    db_latency_ms += elapsed_ms(db_started, minimum=0)

    try:
        remote_started = timer_start()
        response = fetch_blob_bytes(bucket=src, bucket_key=blob.bucket_key)
        body_io = io.BytesIO(response["Body"].read())
        remote_latency_ms += elapsed_ms(remote_started, minimum=0)

        remote_started = timer_start()
        upload_blob(bucket=destination, bucket_key=blob.bucket_key, body=body_io)
        remote_latency_ms += elapsed_ms(remote_started, minimum=0)
    except Exception as exc:
        log.warning(
            "blob_migrate_remote_failed",
            blob_id=str(blob.id),
            destination_bucket=str(destination.id),
            error=str(exc),
        )
        return BlobMigrationResult(
            migrated=False,
            status="failed",
            reason="remote_copy_failed",
            error_class=exc.__class__.__name__,
            error_message=str(exc),
            db_latency_ms=db_latency_ms,
            remote_latency_ms=remote_latency_ms,
        )

    try:
        db_started = timer_start()
        blob.bucket_id = destination.id
        blob.migrated_at = dt.datetime.now(dt.UTC)
        db.flush()
        adjust_bucket_usage_cache(
            src.id, object_count_delta=-1, size_bytes_delta=-blob.size_bytes
        )
        adjust_bucket_usage_cache(
            destination.id, object_count_delta=1, size_bytes_delta=blob.size_bytes
        )
        db.commit()
        db_latency_ms += elapsed_ms(db_started, minimum=0)
    except Exception as exc:
        db.rollback()
        log.warning(
            "blob_migrate_db_commit_failed",
            blob_id=str(blob.id),
            destination_bucket=str(destination.id),
            error=str(exc),
        )
        return BlobMigrationResult(
            migrated=False,
            status="failed",
            reason="db_commit_failed",
            error_class=exc.__class__.__name__,
            error_message=str(exc),
            db_latency_ms=db_latency_ms,
            remote_latency_ms=remote_latency_ms,
        )

    try:
        remote_started = timer_start()
        delete_blob_bytes(bucket=src, bucket_key=blob.bucket_key)
        remote_latency_ms += elapsed_ms(remote_started, minimum=0)
    except (BotoCoreError, ClientError, OSError, ValueError) as exc:
        log.warning(
            "blob_migrate_old_key_delete_failed",
            blob_id=str(blob.id),
            error=str(exc),
        )

    return BlobMigrationResult(
        migrated=True,
        status="succeeded",
        db_latency_ms=db_latency_ms,
        remote_latency_ms=remote_latency_ms,
    )


# ---------------------------------------------------------------------------
# Demote
# ---------------------------------------------------------------------------


def demote_pressured_buckets_batch(
    db: Session,
    *,
    demote_limit: int,
    pressure_ratio: float,
    headroom_ratio: float,
    min_residency_hours: int,
    batch_id: uuid.UUID | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Push oldest blobs out of buckets above the pressure threshold.

    A bucket is "pressured" when current/max >= pressure_ratio. We pick the
    blobs in those buckets ordered by ``accessed_at`` ascending (coldest first)
    and try to move each into the next hotness-ranked bucket below the source
    that still has promotion headroom (i.e. is not itself almost full).
    """
    effective_batch_id = batch_id or uuid.uuid4()
    effective_now = now or dt.datetime.now(dt.UTC)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=dt.UTC)
    residency_cutoff = effective_now - dt.timedelta(hours=min_residency_hours)

    ranked = hotness_ranked_buckets(db)
    if not ranked:
        return {"moved": 0, "skipped": 0, "failed": 0, "scanned": 0}

    bucket_ids = [h.bucket.id for h in ranked]
    usages = get_bucket_usages(db, bucket_ids)

    pressured_ids = {
        h.bucket.id
        for h in ranked
        if h.bucket.max_size_bytes > 0
        and usages[h.bucket.id].current_size_bytes * 1000
        >= int(h.bucket.max_size_bytes * pressure_ratio * 1000)
    }
    if not pressured_ids:
        return {"moved": 0, "skipped": 0, "failed": 0, "scanned": 0}

    blobs = list(
        db.scalars(
            select(Blob)
            .where(Blob.bucket_id.in_(pressured_ids), Blob.refcount > 0)
            .options(selectinload(Blob.files).selectinload(File.folder))
            .order_by(Blob.accessed_at.asc())
            .limit(demote_limit * 8)
        ).unique()
    )

    moved = 0
    skipped = 0
    failed = 0
    for blob in blobs:
        if moved >= demote_limit:
            break
        if not _is_eligible_for_migration(blob, residency_cutoff=residency_cutoff):
            continue

        started_at = timer_start()
        destination = _next_colder_destination(
            ranked,
            from_bucket_id=blob.bucket_id,
            blob=blob,
            usages=usages,
            headroom_ratio=headroom_ratio,
        )
        if destination is None:
            skipped += 1
            create_maintenance_event(
                db,
                job="demote_pressured_buckets",
                action="blob.demotion_skipped",
                status="skipped",
                batch_id=effective_batch_id,
                bucket_id=blob.bucket_id,
                blob_id=blob.id,
                duration_ms=elapsed_ms(started_at, minimum=0),
                metadata={
                    "from_bucket_id": str(blob.bucket_id),
                    "reason": "no_colder_bucket_with_headroom",
                    "size_bytes": blob.size_bytes,
                },
            )
            continue

        from_bucket_id = blob.bucket_id
        to_bucket_id = destination.id
        migration = _migrate_blob_to_bucket_inner(
            db, blob, destination, headroom_ratio=headroom_ratio
        )
        _record_migration_event(
            db,
            job="demote_pressured_buckets",
            success_action="blob.demoted",
            failure_action="blob.demotion_failed",
            skip_action="blob.demotion_skipped",
            migration=migration,
            blob=blob,
            from_bucket_id=from_bucket_id,
            to_bucket_id=to_bucket_id,
            batch_id=effective_batch_id,
            duration_ms=elapsed_ms(started_at, minimum=0),
        )
        if migration.migrated:
            moved += 1
            usages[from_bucket_id] = _usage_after_delta(
                usages[from_bucket_id], -blob.size_bytes
            )
            usages[to_bucket_id] = _usage_after_delta(
                usages[to_bucket_id], blob.size_bytes
            )
        elif migration.status == "failed":
            failed += 1
        else:
            skipped += 1

    log.info(
        "blob_demote_batch",
        moved=moved,
        skipped=skipped,
        failed=failed,
        scanned=len(blobs),
    )
    return {
        "scanned": len(blobs),
        "moved": moved,
        "skipped": skipped,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# Promote
# ---------------------------------------------------------------------------


def promote_recently_accessed_batch(
    db: Session,
    *,
    promote_limit: int,
    headroom_ratio: float,
    recency_days: int,
    min_residency_hours: int,
    batch_id: uuid.UUID | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Bubble recently-touched blobs up toward the hottest bucket with headroom."""
    effective_batch_id = batch_id or uuid.uuid4()
    effective_now = now or dt.datetime.now(dt.UTC)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=dt.UTC)
    recency_cutoff = effective_now - dt.timedelta(days=recency_days)
    residency_cutoff = effective_now - dt.timedelta(hours=min_residency_hours)

    ranked = hotness_ranked_buckets(db)
    if len(ranked) < 2:
        return {"moved": 0, "skipped": 0, "failed": 0, "scanned": 0}
    usages = get_bucket_usages(db, [h.bucket.id for h in ranked])

    blobs = list(
        db.scalars(
            select(Blob)
            .where(Blob.refcount > 0, Blob.accessed_at >= recency_cutoff)
            .options(selectinload(Blob.files).selectinload(File.folder))
            .order_by(Blob.accessed_at.desc())
            .limit(promote_limit * 8)
        ).unique()
    )

    moved = 0
    skipped = 0
    failed = 0
    for blob in blobs:
        if moved >= promote_limit:
            break
        if not _is_eligible_for_migration(blob, residency_cutoff=residency_cutoff):
            continue

        destination = _hotter_destination_with_headroom(
            ranked,
            from_bucket_id=blob.bucket_id,
            blob=blob,
            usages=usages,
            headroom_ratio=headroom_ratio,
            preferred_bucket_id=agreed_preferred_bucket_id(db, blob),
        )
        if destination is None:
            continue

        started_at = timer_start()
        from_bucket_id = blob.bucket_id
        to_bucket_id = destination.id
        migration = _migrate_blob_to_bucket_inner(
            db, blob, destination, headroom_ratio=headroom_ratio
        )
        _record_migration_event(
            db,
            job="promote_recently_accessed",
            success_action="blob.promoted",
            failure_action="blob.promotion_failed",
            skip_action="blob.promotion_skipped",
            migration=migration,
            blob=blob,
            from_bucket_id=from_bucket_id,
            to_bucket_id=to_bucket_id,
            batch_id=effective_batch_id,
            duration_ms=elapsed_ms(started_at, minimum=0),
        )
        if migration.migrated:
            moved += 1
            usages[from_bucket_id] = _usage_after_delta(
                usages[from_bucket_id], -blob.size_bytes
            )
            usages[to_bucket_id] = _usage_after_delta(
                usages[to_bucket_id], blob.size_bytes
            )
        elif migration.status == "failed":
            failed += 1
        else:
            skipped += 1

    log.info(
        "blob_promote_batch",
        moved=moved,
        skipped=skipped,
        failed=failed,
        scanned=len(blobs),
    )
    return {
        "scanned": len(blobs),
        "moved": moved,
        "skipped": skipped,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_eligible_for_migration(blob: Blob, *, residency_cutoff: dt.datetime) -> bool:
    """Skip a blob if it was migrated less than min_residency_hours ago."""
    if blob.migrated_at is None:
        return True
    last = blob.migrated_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=dt.UTC)
    return last <= residency_cutoff


def _next_colder_destination(
    ranked: list[BucketHotness],
    *,
    from_bucket_id: uuid.UUID,
    blob: Blob,
    usages: dict[uuid.UUID, Any],
    headroom_ratio: float,
) -> Bucket | None:
    """First bucket ranked colder than ``from_bucket_id`` that has headroom."""
    seen_source = False
    for hotness in ranked:
        if hotness.bucket.id == from_bucket_id:
            seen_source = True
            continue
        if not seen_source:
            continue
        if _has_headroom(hotness.bucket, usages, blob.size_bytes, headroom_ratio):
            return hotness.bucket
    return None


def _hotter_destination_with_headroom(
    ranked: list[BucketHotness],
    *,
    from_bucket_id: uuid.UUID,
    blob: Blob,
    usages: dict[uuid.UUID, Any],
    headroom_ratio: float,
    preferred_bucket_id: uuid.UUID | None = None,
) -> Bucket | None:
    """Hottest bucket ranked above ``from_bucket_id`` that still has headroom.

    If ``preferred_bucket_id`` is set and is hotter than the source and has
    headroom, prefer it over the absolute hottest. (Power-user override stays
    a hint, not a hard constraint.)
    """
    candidates: list[Bucket] = []
    for hotness in ranked:
        if hotness.bucket.id == from_bucket_id:
            break
        candidates.append(hotness.bucket)
    if not candidates:
        return None

    if preferred_bucket_id is not None:
        for bucket in candidates:
            if bucket.id == preferred_bucket_id and _has_headroom(
                bucket, usages, blob.size_bytes, headroom_ratio
            ):
                return bucket

    for bucket in candidates:
        if _has_headroom(bucket, usages, blob.size_bytes, headroom_ratio):
            return bucket
    return None


def _has_headroom(
    bucket: Bucket,
    usages: dict[uuid.UUID, Any],
    size_bytes: int,
    headroom_ratio: float,
) -> bool:
    usage = usages.get(bucket.id)
    if usage is None:
        return False
    projected = usage.current_size_bytes + size_bytes
    if projected > bucket.max_size_bytes:
        return False
    if headroom_ratio >= 1.0:
        return True
    return projected <= int(bucket.max_size_bytes * headroom_ratio)


def _usage_after_delta(usage: Any, delta_bytes: int) -> Any:
    from services.placement import BucketUsage

    return BucketUsage(
        object_count=max(0, usage.object_count + (1 if delta_bytes > 0 else -1)),
        current_size_bytes=max(0, usage.current_size_bytes + delta_bytes),
    )


def _record_migration_event(
    db: Session,
    *,
    job: str,
    success_action: str,
    failure_action: str,
    skip_action: str,
    migration: BlobMigrationResult,
    blob: Blob,
    from_bucket_id: uuid.UUID,
    to_bucket_id: uuid.UUID,
    batch_id: uuid.UUID,
    duration_ms: int,
) -> None:
    base_meta = {
        "from_bucket_id": str(from_bucket_id),
        "to_bucket_id": str(to_bucket_id),
        "size_bytes": blob.size_bytes,
        "db_latency_ms": migration.db_latency_ms,
        "remote_latency_ms": migration.remote_latency_ms,
        "reason": migration.reason,
    }
    if migration.migrated:
        action = success_action
        status = "succeeded"
    elif migration.status == "failed":
        action = failure_action
        status = "failed"
        if migration.error_class or migration.error_message:
            base_meta["error_class"] = migration.error_class
            base_meta["error_message"] = migration.error_message
    else:
        action = skip_action
        status = "skipped"

    create_maintenance_event(
        db,
        job=job,
        action=action,
        status=status,
        batch_id=batch_id,
        bucket_id=to_bucket_id if migration.migrated else from_bucket_id,
        blob_id=blob.id,
        duration_ms=duration_ms,
        metadata=base_meta,
    )
    db.commit()
