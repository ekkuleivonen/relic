"""Bucket placement and latency-driven hotness ranking.

The system has no static "hot/warm/cold" bucket tier anymore. Instead the
maintenance cron probes every bucket on a schedule and writes timing samples
into ``bucket_probes``. Placement averages the most recent ``PROBE_RANKING_WINDOW``
successful probes per bucket and ranks buckets by their average per-op latency
(lower = hotter). New uploads land in the hottest bucket with capacity; the
demote/promote cron jobs migrate blobs around as access patterns and bucket
fullness change.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from time import monotonic

import settings as S
from domain.exceptions import ConflictError
from domain.storage.hotness import ProbeSample, score_bucket_hotness
from infra.db.models import Blob, Bucket, BucketProbe, Folder
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

_USAGE_CACHE_TTL_SECONDS = 1.0
_UNREACHABLE_SCORE = 10**12


@dataclass(frozen=True)
class BucketUsage:
    object_count: int
    current_size_bytes: int


@dataclass(frozen=True)
class BucketHotness:
    """Aggregated hotness signal for a bucket.

    ``avg_latency_ms`` is the mean across the most recent successful probes
    for the four ops we measure. ``reachable`` reflects whether the bucket has
    any successful probe at all in the ranking window — buckets with zero
    successes get sorted to the bottom of the ranking.
    """

    bucket: Bucket
    avg_latency_ms: float
    reachable: bool
    sample_count: int


_usage_cache: dict[uuid.UUID, tuple[float, BucketUsage]] = {}


# ---------------------------------------------------------------------------
# Hotness ranking
# ---------------------------------------------------------------------------


def hotness_for_buckets(
    db: Session,
    buckets: list[Bucket],
    *,
    window: int | None = None,
) -> dict[uuid.UUID, BucketHotness]:
    """Average the most recent successful probes per bucket within `window`."""
    effective_window = window if window is not None else S.PROBE_RANKING_WINDOW
    if effective_window < 1:
        effective_window = 1

    by_id: dict[uuid.UUID, BucketHotness] = {
        bucket.id: BucketHotness(
            bucket=bucket,
            avg_latency_ms=float(_UNREACHABLE_SCORE),
            reachable=False,
            sample_count=0,
        )
        for bucket in buckets
    }
    if not buckets:
        return by_id

    bucket_ids = list(by_id)
    rows = db.execute(
        select(
            BucketProbe.bucket_id,
            BucketProbe.observed_at,
            BucketProbe.put_ms,
            BucketProbe.head_ms,
            BucketProbe.get_ms,
            BucketProbe.delete_ms,
        )
        .where(BucketProbe.bucket_id.in_(bucket_ids), BucketProbe.success.is_(True))
        .order_by(BucketProbe.bucket_id, desc(BucketProbe.observed_at))
    ).all()

    grouped: dict[uuid.UUID, list[ProbeSample]] = defaultdict(list)
    for bucket_id, _observed_at, put_ms, head_ms, get_ms, delete_ms in rows:
        if len(grouped[bucket_id]) >= effective_window:
            continue
        grouped[bucket_id].append(
            ProbeSample(
                put_ms=put_ms,
                head_ms=head_ms,
                get_ms=get_ms,
                delete_ms=delete_ms,
            )
        )

    bucket_by_id = {bucket.id: bucket for bucket in buckets}
    for bucket_id, samples in grouped.items():
        bucket = bucket_by_id[bucket_id]
        scored = score_bucket_hotness(bucket, samples)
        by_id[bucket_id] = BucketHotness(
            bucket=scored.bucket,
            avg_latency_ms=scored.avg_latency_ms,
            reachable=scored.reachable,
            sample_count=scored.sample_count,
        )

    return by_id


def hotness_ranked_buckets(
    db: Session,
    *,
    window: int | None = None,
) -> list[BucketHotness]:
    """All buckets ordered hottest-first.

    Sort key: (reachable buckets before unreachable, lower avg latency first,
    then bucket name as a deterministic tie breaker).
    """
    buckets = list(db.scalars(select(Bucket).order_by(Bucket.name)))
    by_id = hotness_for_buckets(db, buckets, window=window)
    return sorted(
        by_id.values(),
        key=lambda h: (0 if h.reachable else 1, h.avg_latency_ms, h.bucket.name),
    )


def bucket_is_reachable(db: Session, bucket: Bucket) -> bool:
    """True iff at least one successful probe exists in the ranking window."""
    hotness = hotness_for_buckets(db, [bucket])[bucket.id]
    return hotness.reachable


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def choose_bucket(
    db: Session,
    *,
    size_bytes: int,
    preferred_bucket_id: uuid.UUID | None = None,
    exclude_bucket_ids: set[uuid.UUID] | frozenset[uuid.UUID] | None = None,
    headroom_ratio: float | None = None,
) -> Bucket:
    """Pick a bucket that fits ``size_bytes`` while leaving write headroom.

    Preference order:
      1. The requested ``preferred_bucket_id`` if it exists, isn't excluded,
         and would stay under ``headroom_ratio`` after the write.
      2. Otherwise the hottest bucket (per probe-derived ranking) that
         satisfies the headroom constraint.

    Headroom guards against the user write path saturating a bucket, which
    would otherwise force the demote cron to play catch-up.
    """
    effective_excluded = set(exclude_bucket_ids or ())
    effective_headroom = (
        headroom_ratio if headroom_ratio is not None else S.STORAGE_WRITE_HEADROOM_RATIO
    )
    ranked = hotness_ranked_buckets(db)
    candidates = [h.bucket for h in ranked if h.bucket.id not in effective_excluded]
    if not candidates:
        raise ConflictError("No buckets are configured")

    usages = get_bucket_usages(db, [bucket.id for bucket in candidates])

    def fits(bucket: Bucket) -> bool:
        usage = usages[bucket.id]
        projected = usage.current_size_bytes + size_bytes
        if projected > bucket.max_size_bytes:
            return False
        if effective_headroom is None or effective_headroom >= 1.0:
            return projected <= bucket.max_size_bytes
        return projected <= int(bucket.max_size_bytes * effective_headroom)

    if preferred_bucket_id is not None:
        for bucket in candidates:
            if bucket.id == preferred_bucket_id and fits(bucket):
                return bucket

    for bucket in candidates:
        if fits(bucket):
            return bucket

    raise ConflictError("No bucket has enough capacity")


def agreed_preferred_bucket_id(
    db: Session, blob: Blob
) -> uuid.UUID | None:
    """Effective ``preferred_bucket_id`` for a (possibly deduplicated) blob.

    Returns the preferred bucket only when *all* folders that hold a File
    pointing at the blob agree on the same effective preference (walking the
    ancestor chain). If folders disagree, or no preference is set anywhere in
    any of their ancestor chains, returns None and the blob is placed by the
    plain hotness ranking.
    """
    folder_ids = {file.folder_id for file in blob.files}
    if not folder_ids:
        return None

    seen: set[uuid.UUID | None] = set()
    for folder_id in folder_ids:
        folder = db.get(Folder, folder_id)
        seen.add(_effective_preferred_bucket_id_for_folder(db, folder))

    seen.discard(None)
    if len(seen) == 1:
        return next(iter(seen))
    return None


def _effective_preferred_bucket_id_for_folder(
    db: Session, folder: Folder | None
) -> uuid.UUID | None:
    current = folder
    visited: set[uuid.UUID] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        if current.preferred_bucket_id is not None:
            return current.preferred_bucket_id
        if current.parent_id is None:
            return None
        current = db.get(Folder, current.parent_id)
    return None


def effective_preferred_bucket_id(db: Session, folder: Folder) -> uuid.UUID | None:
    """Public form of the folder-chain walk for API serialization."""
    return _effective_preferred_bucket_id_for_folder(db, folder)


# ---------------------------------------------------------------------------
# Bucket usage cache (unchanged)
# ---------------------------------------------------------------------------


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


# Imported here to keep mypy happy with forward refs in agreed_preferred_bucket_id.
__all__ = [
    "BucketUsage",
    "BucketHotness",
    "hotness_for_buckets",
    "hotness_ranked_buckets",
    "bucket_is_reachable",
    "choose_bucket",
    "agreed_preferred_bucket_id",
    "effective_preferred_bucket_id",
    "get_bucket_usage",
    "get_bucket_usages",
    "derive_bucket_usages",
    "adjust_bucket_usage_cache",
    "clear_bucket_usage_cache",
]
