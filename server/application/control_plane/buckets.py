import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.exceptions import BadRequestError, ResourceNotFound
from infra.db.models import Bucket, BucketProbe
from application.control_plane.placement import (
    BucketHotness,
    BucketUsage,
    clear_bucket_usage_cache,
    derive_bucket_usages,
    hotness_for_buckets,
)
from utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class BucketProbeResult:
    """One probe pass against a bucket: timings + the bucket itself."""

    bucket: Bucket
    probe: BucketProbe
    reachable: bool


def list_buckets(db: Session) -> list[Bucket]:
    return list(db.scalars(select(Bucket).order_by(Bucket.name)))


def list_bucket_reads(db: Session) -> list[dict[str, Any]]:
    buckets = list_buckets(db)
    usages = derive_bucket_usages(db, [bucket.id for bucket in buckets])
    hotness = hotness_for_buckets(db, buckets)
    return [
        bucket_read(bucket, usages[bucket.id], hotness[bucket.id])
        for bucket in buckets
    ]


def get_bucket(db: Session, bucket_id: uuid.UUID) -> Bucket:
    bucket = db.get(Bucket, bucket_id)
    if not bucket:
        raise ResourceNotFound("Bucket not found")
    return bucket


def get_bucket_read(db: Session, bucket_id: uuid.UUID) -> dict[str, Any]:
    bucket = get_bucket(db, bucket_id)
    return bucket_read(
        bucket,
        derive_bucket_usages(db, [bucket.id])[bucket.id],
        hotness_for_buckets(db, [bucket])[bucket.id],
    )


def bucket_read(
    bucket: Bucket, usage: BucketUsage, hotness: BucketHotness
) -> dict[str, Any]:
    return {
        "id": bucket.id,
        "name": bucket.name,
        "endpoint": bucket.endpoint,
        "region": bucket.region,
        "bucket": bucket.bucket,
        "key_id": bucket.key_id,
        "secret_access_key": bucket.secret_access_key,
        "max_size_bytes": bucket.max_size_bytes,
        "storage_kind": bucket.storage_kind,
        "object_count": usage.object_count,
        "current_size_bytes": usage.current_size_bytes,
        "avg_latency_ms": (
            round(hotness.avg_latency_ms, 2) if hotness.reachable else None
        ),
        "probe_sample_count": hotness.sample_count,
        "reachable": hotness.reachable,
    }


def timed_ms(operation) -> int:
    started = time.perf_counter()
    operation()
    return max(1, round((time.perf_counter() - started) * 1000))
