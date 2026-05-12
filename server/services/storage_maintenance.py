"""
Background blob lifecycle: purge dereferenced blobs, bucket probes, and rebalancing.

See workers called from parsers/worker.py (arq cron).
"""

import datetime as dt
import io
import uuid
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models import Blob, Bucket, File
from schema_plan import BucketTier
from services import buckets as bucket_service
from services.events import EventContext, create_event
from services.folder_storage_policy import effective_cooldown_days, effective_min_tier
from services.objects import delete_blob_bytes, fetch_blob_bytes, upload_blob
from services.placement import (
    adjust_bucket_usage_cache,
    choose_bucket,
    get_bucket_usages,
)
from utils.logging import get_logger

log = get_logger(__name__)


def purge_dereferenced_blobs_batch(
    db: Session,
    *,
    batch: int,
    event_context: EventContext | None = None,
) -> dict[str, Any]:
    """
    For blobs with refcount < 1, delete remote keys and Blob rows.

    Uses row-level SKIP LOCKED when supported (PostgreSQL / recent SQLite).
    """
    dialect = db.get_bind().dialect.name
    stmt = (
        select(Blob)
        .where(Blob.refcount < 1)
        .order_by(Blob.updated_at.asc(), Blob.created_at.asc())
        .limit(batch)
    )
    if dialect in ("postgresql", "sqlite"):
        stmt = stmt.with_for_update(skip_locked=True)
    blobs = list(db.scalars(stmt))

    deleted_rows = 0
    freed_bytes = 0
    errors = 0
    deleted_blob_ids: list[uuid.UUID] = []
    failed_blob_ids: list[uuid.UUID] = []
    for blob in blobs:
        try:
            with db.begin_nested():
                bucket = db.get(Bucket, blob.bucket_id)
                if bucket is not None:
                    try:
                        delete_blob_bytes(bucket=bucket, bucket_key=blob.bucket_key)
                    except (BotoCoreError, ClientError, OSError, ValueError) as exc:
                        log.warning(
                            "blob_purge_remote_delete_failed",
                            blob_id=str(blob.id),
                            bucket_id=str(blob.bucket_id),
                            error=str(exc),
                        )
                        raise
                    adjust_bucket_usage_cache(
                        bucket.id,
                        object_count_delta=-1,
                        size_bytes_delta=-blob.size_bytes,
                    )
                freed_bytes += int(blob.size_bytes)
                deleted_rows += 1
                deleted_blob_ids.append(blob.id)
                db.delete(blob)
        except Exception:
            errors += 1
            failed_blob_ids.append(blob.id)

    should_emit_event = event_context is not None and (
        deleted_rows > 0 or errors > 0
    )
    if should_emit_event:
        create_event(
            db,
            source=event_context.source,
            operation="blob.purged",
            status="failed" if errors else "succeeded",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            blob_ids=[*deleted_blob_ids, *failed_blob_ids],
            metadata={
                "scanned": len(blobs),
                "deleted_rows": deleted_rows,
                "freed_bytes": freed_bytes,
                "errors": errors,
                "failed_blob_ids": [str(blob_id) for blob_id in failed_blob_ids],
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


def probe_all_buckets(
    db: Session, *, event_context: EventContext | None = None
) -> dict[str, Any]:
    buckets = bucket_service.list_buckets(db)
    ok = 0
    failed = 0
    for b in buckets:
        try:
            bucket_service.probe_bucket(db, b.id, event_context=event_context)
            ok += 1
        except Exception as exc:
            failed += 1
            log.warning(
                "bucket_probe_failed_in_batch",
                bucket_id=str(b.id),
                error=str(exc),
            )
    return {"bucket_count": len(buckets), "ok": ok, "failed": failed}


def _tier_floor_for_blob(db: Session, blob: Blob) -> int:
    tiers: list[int] = []
    for f in blob.files:
        tiers.append(effective_min_tier(db, f.folder))
    return max(tiers) if tiers else int(BucketTier.HOT)


def _max_idle_cooldown_for_blob(db: Session, blob: Blob) -> int | None:
    cds: list[int] = []
    for f in blob.files:
        cd = effective_cooldown_days(db, f.folder)
        if cd is not None:
            cds.append(cd)
    return max(cds) if cds else None


def _target_tier_for_policy(
    db: Session,
    blob: Blob,
    *,
    now: dt.datetime | None = None,
) -> int | None:
    """Returns a colder tier value (> current bucket.tier) or None if no move needed."""
    effective_now = now or dt.datetime.now(dt.UTC)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=dt.UTC)

    bucket = blob.bucket
    if bucket is None:
        return None

    floor = _tier_floor_for_blob(db, blob)
    if bucket.tier < floor:
        return floor

    accessed = blob.accessed_at
    if accessed.tzinfo is None:
        accessed = accessed.replace(tzinfo=dt.UTC)

    cooldown = _max_idle_cooldown_for_blob(db, blob)
    target_after_idle = bucket.tier
    if cooldown is not None and (effective_now - accessed) >= dt.timedelta(
        days=cooldown
    ):
        target_after_idle = max(
            floor, min(int(BucketTier.FROZEN), bucket.tier + 1)
        )

    desired = max(floor, target_after_idle)
    if desired <= bucket.tier:
        return None
    return desired


def _migrate_blob_to_bucket_inner(
    db: Session,
    blob: Blob,
    destination: Bucket,
) -> bool:
    if destination.id == blob.bucket_id:
        return False

    src = db.get(Bucket, blob.bucket_id)
    if src is None:
        return False

    destination_usage = get_bucket_usages(db, [destination.id])[destination.id]
    if destination_usage.current_size_bytes + blob.size_bytes > destination.max_size_bytes:
        log.warning(
            "blob_migrate_destination_full",
            blob_id=str(blob.id),
            dest_bucket=str(destination.id),
        )
        return False

    try:
        response = fetch_blob_bytes(bucket=src, bucket_key=blob.bucket_key)
        body_io = io.BytesIO(response["Body"].read())

        upload_blob(bucket=destination, bucket_key=blob.bucket_key, body=body_io)

        try:
            delete_blob_bytes(bucket=src, bucket_key=blob.bucket_key)
        except (BotoCoreError, ClientError, OSError, ValueError) as exc:
            log.warning(
                "blob_migrate_old_key_delete_failed",
                blob_id=str(blob.id),
                error=str(exc),
            )
            raise

        blob.bucket_id = destination.id
        db.flush()
        adjust_bucket_usage_cache(
            src.id, object_count_delta=-1, size_bytes_delta=-blob.size_bytes
        )
        adjust_bucket_usage_cache(
            destination.id, object_count_delta=1, size_bytes_delta=blob.size_bytes
        )
    except Exception as exc:
        log.warning(
            "blob_migrate_failed",
            blob_id=str(blob.id),
            destination_bucket=str(destination.id),
            error=str(exc),
        )
        return False

    return True


def _pick_destination_same_tier(
    db: Session,
    *,
    blob: Blob,
    tier_int: int,
    exclude_bucket_ids: set[uuid.UUID],
) -> Bucket | None:
    try:
        return choose_bucket(
            db,
            tier=BucketTier(tier_int),
            size_bytes=blob.size_bytes,
            exclude_bucket_ids=exclude_bucket_ids,
        )
    except Exception:
        return None


def rebalance_blob_storage_batch(
    db: Session,
    *,
    migrate_limit: int,
    pressure_ratio: float,
    event_context: EventContext | None = None,
) -> dict[str, Any]:
    """
    Migrate blobs according to lifecycle (folder min tier + cooldown) and bucket
    pressure. Pressure is evaluated jointly: overflow tries same-tier spill then
    progressively colder tiers respecting the lifecycle floor.
    """
    buckets = list(db.scalars(select(Bucket)))
    bucket_usages = get_bucket_usages(db, [bucket.id for bucket in buckets])
    overcrowded_ids: set[uuid.UUID] = {
        bucket.id
        for bucket in buckets
        if bucket.max_size_bytes > 0
        and bucket_usages[bucket.id].current_size_bytes * 1000
        >= int(bucket.max_size_bytes * pressure_ratio * 1000)
    }

    moved = 0
    skipped = 0
    blobs = list(
        db.scalars(
            select(Blob)
            .where(Blob.refcount > 0)
            .options(selectinload(Blob.files).selectinload(File.folder))
            .order_by(Blob.accessed_at.asc())
            .limit(migrate_limit * 8)
        ).unique()
    )

    for blob in blobs:
        if moved >= migrate_limit:
            break

        bucket = blob.bucket
        if bucket is None:
            skipped += 1
            continue

        tier_floor = _tier_floor_for_blob(db, blob)
        dest: Bucket | None = None

        lifecycle_target = _target_tier_for_policy(db, blob)
        if lifecycle_target is not None and lifecycle_target > bucket.tier:
            try:
                dest = choose_bucket(
                    db,
                    tier=BucketTier(lifecycle_target),
                    size_bytes=blob.size_bytes,
                    exclude_bucket_ids={bucket.id},
                )
            except Exception:
                dest = None

        if dest is None and bucket.id in overcrowded_ids:
            dest = _pick_destination_same_tier(
                db,
                blob=blob,
                tier_int=bucket.tier,
                exclude_bucket_ids={bucket.id},
            )
            t_scan = bucket.tier
            while dest is None and t_scan < int(BucketTier.FROZEN):
                t_scan += 1
                if t_scan < tier_floor:
                    continue
                exclude: set[uuid.UUID] = (
                    {bucket.id} if t_scan == bucket.tier else set()
                )
                try:
                    dest = choose_bucket(
                        db,
                        tier=BucketTier(t_scan),
                        size_bytes=blob.size_bytes,
                        exclude_bucket_ids=exclude,
                    )
                except Exception:
                    dest = None
                if dest is not None:
                    break

        if dest is None or dest.id == bucket.id:
            skipped += 1
            continue

        source_bucket_id = bucket.id
        if _migrate_blob_to_bucket_inner(db, blob, dest):
            if event_context is not None:
                create_event(
                    db,
                    source=event_context.source,
                    operation="blob.migrated",
                    actor_user_id=event_context.actor_user_id,
                    request_id=event_context.request_id,
                    blob_ids=[blob.id],
                    metadata={
                        "source_bucket_id": str(source_bucket_id),
                        "destination_bucket_id": str(dest.id),
                        "size_bytes": blob.size_bytes,
                    },
                )
            moved += 1
            db.commit()
        else:
            db.rollback()
            skipped += 1

    log.info(
        "blob_rebalance_batch",
        moved=moved,
        skipped=skipped,
        migrate_limit=migrate_limit,
        pressure_ratio=pressure_ratio,
    )
    return {"moved": moved, "skipped": skipped}
