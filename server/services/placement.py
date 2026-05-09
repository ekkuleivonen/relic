from sqlalchemy import select
from sqlalchemy.orm import Session

from managers.exceptions import ConflictError
from models import Bucket
from schema_plan import BucketTier


def choose_bucket(db: Session, *, tier: BucketTier, size_bytes: int) -> Bucket:
    candidates = list(
        db.scalars(
            select(Bucket)
            .where(Bucket.tier == tier)
            .where(Bucket.current_size_bytes + size_bytes <= Bucket.max_size_bytes)
        )
    )
    if not candidates:
        raise ConflictError("No bucket has enough capacity")

    return min(candidates, key=placement_score)


def placement_score(bucket: Bucket) -> tuple[int, int, str]:
    return (
        0 if bucket_is_healthy(bucket) else 1,
        probe_latency_score(bucket),
        bucket.name,
    )


def bucket_is_healthy(bucket: Bucket) -> bool:
    return all(
        latency is not None
        for latency in (
            bucket.probe_latency_put_ms,
            bucket.probe_latency_head_ms,
            bucket.probe_latency_get_ms,
            bucket.probe_latency_delete_ms,
        )
    )


def probe_latency_score(bucket: Bucket) -> int:
    latencies = [
        latency
        for latency in (
            bucket.probe_latency_put_ms,
            bucket.probe_latency_head_ms,
            bucket.probe_latency_get_ms,
            bucket.probe_latency_delete_ms,
        )
        if latency is not None
    ]
    if not latencies:
        return 10**12
    return sum(latencies)
