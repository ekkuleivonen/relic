import time
import uuid
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.exceptions import BadRequestError, ConflictError, ResourceNotFound
from models import Blob, Bucket
from services.audit_events import (
    create_audit_event,
    elapsed_ms,
    latency_metadata,
    timer_start,
)
from services.event_context import EventContext
from services.placement import (
    BucketUsage,
    clear_bucket_usage_cache,
    derive_bucket_usages,
)
from utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class BucketProbeResult:
    bucket: Bucket
    reachable: bool


def list_buckets(db: Session) -> list[Bucket]:
    return list(db.scalars(select(Bucket).order_by(Bucket.name)))


def list_bucket_reads(db: Session) -> list[dict[str, Any]]:
    buckets = list_buckets(db)
    usages = derive_bucket_usages(db, [bucket.id for bucket in buckets])
    return [bucket_read(bucket, usages[bucket.id]) for bucket in buckets]


def get_bucket(db: Session, bucket_id: uuid.UUID) -> Bucket:
    bucket = db.get(Bucket, bucket_id)
    if not bucket:
        raise ResourceNotFound("Bucket not found")
    return bucket


def get_bucket_read(db: Session, bucket_id: uuid.UUID) -> dict[str, Any]:
    bucket = get_bucket(db, bucket_id)
    return bucket_read(bucket, derive_bucket_usages(db, [bucket.id])[bucket.id])


def create_bucket(
    db: Session, values: dict[str, Any], *, event_context: EventContext | None = None
) -> Bucket:
    started_at = timer_start()
    db_started = timer_start()
    ensure_bucket_name_available(db, values["name"])
    bucket = Bucket(**values)
    db.add(bucket)
    db.flush()
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    if event_context is not None:
        create_audit_event(
            db,
            operation="bucket.created",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            metadata={
                "bucket_id": str(bucket.id),
                "name": bucket.name,
                "tier": int(bucket.tier),
                **latency_metadata(started_at, db_latency_ms=db_latency_ms),
            },
        )
    db.commit()
    db.refresh(bucket)
    return bucket


def create_bucket_read(
    db: Session, values: dict[str, Any], *, event_context: EventContext | None = None
) -> dict[str, Any]:
    bucket = create_bucket(db, values, event_context=event_context)
    return bucket_read(bucket, derive_bucket_usages(db, [bucket.id])[bucket.id])


def update_bucket(
    db: Session,
    bucket_id: uuid.UUID,
    values: dict[str, Any],
    *,
    event_context: EventContext | None = None,
) -> Bucket:
    started_at = timer_start()
    db_started = timer_start()
    bucket = get_bucket(db, bucket_id)
    if "name" in values:
        ensure_bucket_name_available(db, values["name"], excluding_id=bucket.id)

    for key, value in values.items():
        setattr(bucket, key, value)

    db.flush()
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    if event_context is not None:
        create_audit_event(
            db,
            operation="bucket.updated",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            metadata={
                "bucket_id": str(bucket.id),
                "name": bucket.name,
                "changed_fields": sorted(values),
                **latency_metadata(started_at, db_latency_ms=db_latency_ms),
            },
        )
    db.commit()
    db.refresh(bucket)
    return bucket


def update_bucket_read(
    db: Session,
    bucket_id: uuid.UUID,
    values: dict[str, Any],
    *,
    event_context: EventContext | None = None,
) -> dict[str, Any]:
    bucket = update_bucket(db, bucket_id, values, event_context=event_context)
    return bucket_read(bucket, derive_bucket_usages(db, [bucket.id])[bucket.id])


def delete_bucket(
    db: Session, bucket_id: uuid.UUID, *, event_context: EventContext | None = None
) -> None:
    started_at = timer_start()
    db_started = timer_start()
    bucket = get_bucket(db, bucket_id)
    blob_count = db.scalar(
        select(func.count()).select_from(Blob).where(Blob.bucket_id == bucket.id)
    )
    if blob_count:
        raise ConflictError(
            "Bucket still has blobs",
            detail={"message": "Bucket still has blobs", "blob_count": blob_count},
        )

    metadata = {"bucket_id": str(bucket.id), "name": bucket.name, "tier": int(bucket.tier)}
    db.delete(bucket)
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    if event_context is not None:
        create_audit_event(
            db,
            operation="bucket.deleted",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            metadata={
                **metadata,
                **latency_metadata(started_at, db_latency_ms=db_latency_ms),
            },
        )
    db.commit()
    clear_bucket_usage_cache(bucket.id)


def bucket_read(bucket: Bucket, usage: BucketUsage) -> dict[str, Any]:
    return {
        "id": bucket.id,
        "name": bucket.name,
        "endpoint": bucket.endpoint,
        "region": bucket.region,
        "bucket": bucket.bucket,
        "key_id": bucket.key_id,
        "secret_access_key": bucket.secret_access_key,
        "tier": bucket.tier,
        "max_size_bytes": bucket.max_size_bytes,
        "object_count": usage.object_count,
        "current_size_bytes": usage.current_size_bytes,
        "probe_latency_put_ms": bucket.probe_latency_put_ms,
        "probe_latency_head_ms": bucket.probe_latency_head_ms,
        "probe_latency_get_ms": bucket.probe_latency_get_ms,
        "probe_latency_delete_ms": bucket.probe_latency_delete_ms,
    }


def probe_bucket(db: Session, bucket_id: uuid.UUID) -> BucketProbeResult:
    bucket = get_bucket(db, bucket_id)
    probe_key = f"__relic_probe__/{uuid.uuid4()}"
    probe_body = b"relic-probe"
    reachable = True

    try:
        client = boto3.client(
            "s3",
            endpoint_url=bucket.endpoint,
            region_name=bucket.region,
            aws_access_key_id=bucket.key_id,
            aws_secret_access_key=bucket.secret_access_key,
        )
        bucket.probe_latency_put_ms = timed_ms(
            lambda: client.put_object(Bucket=bucket.bucket, Key=probe_key, Body=probe_body)
        )
        bucket.probe_latency_head_ms = timed_ms(
            lambda: client.head_object(Bucket=bucket.bucket, Key=probe_key)
        )
        bucket.probe_latency_get_ms = timed_ms(
            lambda: client.get_object(Bucket=bucket.bucket, Key=probe_key)["Body"].read()
        )
        bucket.probe_latency_delete_ms = timed_ms(
            lambda: client.delete_object(Bucket=bucket.bucket, Key=probe_key)
        )
    except (BotoCoreError, ClientError, OSError, ValueError) as exc:
        reachable = False
        log.warning(
            "bucket_probe_failed",
            bucket_id=str(bucket.id),
            error=str(exc),
        )
    db.commit()
    db.refresh(bucket)
    return BucketProbeResult(bucket=bucket, reachable=reachable)


def timed_ms(operation) -> int:
    started = time.perf_counter()
    operation()
    return max(1, round((time.perf_counter() - started) * 1000))


def drain_bucket(db: Session, bucket_id: uuid.UUID) -> None:
    get_bucket(db, bucket_id)
    raise BadRequestError("Bucket drain requires the background migration worker")


def ensure_bucket_name_available(
    db: Session, name: str, *, excluding_id: uuid.UUID | None = None
) -> None:
    existing = db.scalar(select(Bucket).where(Bucket.name == name))
    if existing and existing.id != excluding_id:
        raise ConflictError("A bucket with this name already exists")
