import uuid
from dataclasses import dataclass
from time import monotonic

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from managers.exceptions import ConflictError
from models import Blob, Bucket
from schema_plan import BucketTier

_USAGE_CACHE_TTL_SECONDS = 1.0


@dataclass(frozen=True)
class BucketUsage:
    object_count: int
    current_size_bytes: int


_usage_cache: dict[uuid.UUID, tuple[float, BucketUsage]] = {}


def choose_bucket(
    db: Session,
    *,
    tier: BucketTier,
    size_bytes: int,
    exclude_bucket_ids: set[uuid.UUID] | frozenset[uuid.UUID] | None = None,
) -> Bucket:
    q = select(Bucket).where(Bucket.tier == tier)
    if exclude_bucket_ids:
        q = q.where(Bucket.id.not_in(exclude_bucket_ids))
    buckets = list(db.scalars(q))
    usages = get_bucket_usages(db, [bucket.id for bucket in buckets])
    candidates = [
        bucket
        for bucket in buckets
        if usages[bucket.id].current_size_bytes + size_bytes <= bucket.max_size_bytes
    ]
    if not candidates:
        raise ConflictError("No bucket has enough capacity")

    return min(candidates, key=placement_score)


def get_bucket_usage(db: Session, bucket_id: uuid.UUID) -> BucketUsage:
    return get_bucket_usages(db, [bucket_id])[bucket_id]


def derive_bucket_usages(
    db: Session, bucket_ids: list[uuid.UUID] | tuple[uuid.UUID, ...] | set[uuid.UUID]
) -> dict[uuid.UUID, BucketUsage]:
    result = {
        bucket_id: BucketUsage(object_count=0, current_size_bytes=0)
        for bucket_id in bucket_ids
    }
    if not result:
        return result

    rows = db.execute(
        select(
            Blob.bucket_id,
            func.count(Blob.id),
            func.coalesce(func.sum(Blob.size_bytes), 0),
        )
        .where(Blob.bucket_id.in_(list(result)))
        .group_by(Blob.bucket_id)
    ).all()
    for bucket_id, object_count, size_bytes in rows:
        result[bucket_id] = BucketUsage(
            object_count=int(object_count), current_size_bytes=int(size_bytes)
        )
    return result


def get_bucket_usages(
    db: Session, bucket_ids: list[uuid.UUID] | tuple[uuid.UUID, ...] | set[uuid.UUID]
) -> dict[uuid.UUID, BucketUsage]:
    now = monotonic()
    result: dict[uuid.UUID, BucketUsage] = {}
    missing: list[uuid.UUID] = []

    for bucket_id in bucket_ids:
        cached = _usage_cache.get(bucket_id)
        if cached is not None and cached[0] > now:
            result[bucket_id] = cached[1]
        else:
            missing.append(bucket_id)

    if missing:
        fresh = derive_bucket_usages(db, missing)
        expires_at = now + _USAGE_CACHE_TTL_SECONDS
        for bucket_id in missing:
            usage = fresh[bucket_id]
            _usage_cache[bucket_id] = (expires_at, usage)
            result[bucket_id] = usage

    return result


def adjust_bucket_usage_cache(
    bucket_id: uuid.UUID, *, object_count_delta: int, size_bytes_delta: int
) -> None:
    cached = _usage_cache.get(bucket_id)
    if cached is None or cached[0] <= monotonic():
        return

    usage = cached[1]
    _usage_cache[bucket_id] = (
        cached[0],
        BucketUsage(
            object_count=max(0, usage.object_count + object_count_delta),
            current_size_bytes=max(0, usage.current_size_bytes + size_bytes_delta),
        ),
    )


def clear_bucket_usage_cache(bucket_id: uuid.UUID | None = None) -> None:
    if bucket_id is None:
        _usage_cache.clear()
        return
    _usage_cache.pop(bucket_id, None)


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
