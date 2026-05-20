import uuid
from typing import Any

from application.context import EventContext
from infra.db.stores.bucket_probe import probe_bucket as run_bucket_probe
from infra.db.stores.bucket_reads import BucketProbeResult
from infra.db.stores.placement import clear_bucket_usage_cache
from application.uow import UnitOfWork
from domain.exceptions import ConflictError
from ports.entities import Bucket
from utils.logging import get_logger
from utils.timing import elapsed_ms, latency_metadata, timer_start

log = get_logger(__name__)


def create_bucket(
    uow: UnitOfWork,
    values: dict[str, Any],
    *,
    event_context: EventContext | None = None,
) -> Bucket:
    started_at = timer_start()
    db_started = timer_start()
    uow.buckets.ensure_name_available(values["name"])
    bucket = Bucket(**values)
    uow.buckets.add(bucket)
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    uow.audit.record(
        operation="bucket.created",
        event_context=event_context,
        metadata={
            "bucket_id": str(bucket.id),
            "name": bucket.name,
            **latency_metadata(started_at, db_latency_ms=db_latency_ms),
        },
        db_latency_ms=db_latency_ms,
    )
    log.info("bucket_create", bucket_id=str(bucket.id), name=bucket.name)
    return bucket


def update_bucket(
    uow: UnitOfWork,
    bucket_id: uuid.UUID,
    values: dict[str, Any],
    *,
    event_context: EventContext | None = None,
) -> Bucket:
    started_at = timer_start()
    db_started = timer_start()
    bucket = uow.buckets.get(bucket_id)
    if "name" in values:
        uow.buckets.ensure_name_available(values["name"], excluding_id=bucket.id)
    uow.buckets.apply_updates(bucket, values)
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    uow.audit.record(
        operation="bucket.updated",
        event_context=event_context,
        metadata={
            "bucket_id": str(bucket.id),
            "name": bucket.name,
            "changed_fields": sorted(values),
            **latency_metadata(started_at, db_latency_ms=db_latency_ms),
        },
        db_latency_ms=db_latency_ms,
    )
    log.info("bucket_update", bucket_id=str(bucket.id), name=bucket.name)
    return bucket


def delete_bucket(
    uow: UnitOfWork,
    bucket_id: uuid.UUID,
    *,
    event_context: EventContext | None = None,
) -> None:
    started_at = timer_start()
    db_started = timer_start()
    bucket = uow.buckets.get(bucket_id)
    blob_count = uow.buckets.blob_count(bucket.id)
    if blob_count:
        raise ConflictError(
            "Bucket still has blobs",
            detail={"message": "Bucket still has blobs", "blob_count": blob_count},
        )

    metadata = {"bucket_id": str(bucket.id), "name": bucket.name}
    uow.buckets.delete(bucket)
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    uow.audit.record(
        operation="bucket.deleted",
        event_context=event_context,
        metadata={
            **metadata,
            **latency_metadata(started_at, db_latency_ms=db_latency_ms),
        },
        db_latency_ms=db_latency_ms,
    )
    clear_bucket_usage_cache(bucket.id)
    log.info("bucket_delete", bucket_id=str(bucket.id), name=bucket.name)


def probe_bucket(uow: UnitOfWork, bucket_id: uuid.UUID) -> BucketProbeResult:
    return run_bucket_probe(uow, bucket_id)
