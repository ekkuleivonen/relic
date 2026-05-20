import uuid
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from application.context import EventContext
from application.control_plane.buckets import BucketProbeResult, timed_ms
from application.control_plane.placement import clear_bucket_usage_cache
from application.uow import UnitOfWork
from domain.exceptions import ConflictError
from infra.db.models import Bucket, BucketProbe
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
    bucket = uow.buckets.get(bucket_id)
    probe_key = f"__relic_probe__/{uuid.uuid4()}"
    probe_body = b"relic-probe"
    put_ms: int | None = None
    head_ms: int | None = None
    get_ms: int | None = None
    delete_ms: int | None = None
    reachable = True

    try:
        client = boto3.client(
            "s3",
            endpoint_url=bucket.endpoint,
            region_name=bucket.region,
            aws_access_key_id=bucket.key_id,
            aws_secret_access_key=bucket.secret_access_key,
        )
        put_ms = timed_ms(
            lambda: client.put_object(
                Bucket=bucket.bucket, Key=probe_key, Body=probe_body
            )
        )
        head_ms = timed_ms(
            lambda: client.head_object(Bucket=bucket.bucket, Key=probe_key)
        )
        get_ms = timed_ms(
            lambda: client.get_object(Bucket=bucket.bucket, Key=probe_key)["Body"].read()
        )
        delete_ms = timed_ms(
            lambda: client.delete_object(Bucket=bucket.bucket, Key=probe_key)
        )
    except (BotoCoreError, ClientError, OSError, ValueError) as exc:
        reachable = False
        log.warning(
            "bucket_probe_failed",
            bucket_id=str(bucket.id),
            error=str(exc),
        )

    probe = BucketProbe(
        bucket_id=bucket.id,
        success=reachable,
        put_ms=put_ms,
        head_ms=head_ms,
        get_ms=get_ms,
        delete_ms=delete_ms,
    )
    uow.buckets.add_probe(probe)
    uow.session.refresh(bucket)
    uow.session.refresh(probe)
    return BucketProbeResult(bucket=bucket, probe=probe, reachable=reachable)
