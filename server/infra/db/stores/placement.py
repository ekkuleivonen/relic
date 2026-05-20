"""StorageBackend placement and latency-driven hotness ranking.

The system has no static "hot/warm/cold" bucket tier anymore. Instead the
maintenance cron probes every bucket on a schedule and writes timing samples
into ``storage_backend_probes``. Placement averages the most recent ``PROBE_RANKING_WINDOW``
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
from domain.storage.hotness import ProbeSample, score_storage_backend_hotness
from infra.db.models import Blob, StorageBackend, StorageBackendProbe, Folder
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

_USAGE_CACHE_TTL_SECONDS = 1.0
_UNREACHABLE_SCORE = 10**12


@dataclass(frozen=True)
class StorageBackendUsage:
    object_count: int
    current_size_bytes: int


@dataclass(frozen=True)
class StorageBackendHotness:
    """Aggregated hotness signal for a storage backend.

    ``avg_latency_ms`` is the mean across the most recent successful probes
    for the four ops we measure. ``reachable`` reflects whether the backend has
    any successful probe at all in the ranking window — backends with zero
    successes get sorted to the bottom of the ranking.
    """

    storage_backend: StorageBackend
    avg_latency_ms: float
    reachable: bool
    sample_count: int


_usage_cache: dict[uuid.UUID, tuple[float, StorageBackendUsage]] = {}


# ---------------------------------------------------------------------------
# Hotness ranking
# ---------------------------------------------------------------------------


def hotness_for_storage_backends(
    db: Session,
    buckets: list[StorageBackend],
    *,
    window: int | None = None,
) -> dict[uuid.UUID, StorageBackendHotness]:
    """Average the most recent successful probes per bucket within `window`."""
    effective_window = window if window is not None else S.PROBE_RANKING_WINDOW
    if effective_window < 1:
        effective_window = 1

    by_id: dict[uuid.UUID, StorageBackendHotness] = {
        bucket.id: StorageBackendHotness(
            storage_backend=bucket,
            avg_latency_ms=float(_UNREACHABLE_SCORE),
            reachable=False,
            sample_count=0,
        )
        for bucket in buckets
    }
    if not buckets:
        return by_id

    storage_backend_ids = list(by_id)
    rows = db.execute(
        select(
            StorageBackendProbe.storage_backend_id,
            StorageBackendProbe.observed_at,
            StorageBackendProbe.put_ms,
            StorageBackendProbe.head_ms,
            StorageBackendProbe.get_ms,
            StorageBackendProbe.delete_ms,
        )
        .where(StorageBackendProbe.storage_backend_id.in_(storage_backend_ids), StorageBackendProbe.success.is_(True))
        .order_by(StorageBackendProbe.storage_backend_id, desc(StorageBackendProbe.observed_at))
    ).all()

    grouped: dict[uuid.UUID, list[ProbeSample]] = defaultdict(list)
    for storage_backend_id, _observed_at, put_ms, head_ms, get_ms, delete_ms in rows:
        if len(grouped[storage_backend_id]) >= effective_window:
            continue
        grouped[storage_backend_id].append(
            ProbeSample(
                put_ms=put_ms,
                head_ms=head_ms,
                get_ms=get_ms,
                delete_ms=delete_ms,
            )
        )

    bucket_by_id = {bucket.id: bucket for bucket in buckets}
    for storage_backend_id, samples in grouped.items():
        bucket = bucket_by_id[storage_backend_id]
        scored = score_storage_backend_hotness(bucket, samples)
        by_id[storage_backend_id] = StorageBackendHotness(
            storage_backend=scored.storage_backend,
            avg_latency_ms=scored.avg_latency_ms,
            reachable=scored.reachable,
            sample_count=scored.sample_count,
        )

    return by_id


def hotness_ranked_storage_backends(
    db: Session,
    *,
    window: int | None = None,
) -> list[StorageBackendHotness]:
    """All buckets ordered hottest-first.

    Sort key: (reachable buckets before unreachable, lower avg latency first,
    then bucket name as a deterministic tie breaker).
    """
    buckets = list(db.scalars(select(StorageBackend).order_by(StorageBackend.name)))
    by_id = hotness_for_storage_backends(db, buckets, window=window)
    return sorted(
        by_id.values(),
        key=lambda h: (0 if h.reachable else 1, h.avg_latency_ms, h.storage_backend.name),
    )


def storage_backend_is_reachable(db: Session, bucket: StorageBackend) -> bool:
    """True iff at least one successful probe exists in the ranking window."""
    hotness = hotness_for_storage_backends(db, [bucket])[bucket.id]
    return hotness.reachable


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def choose_storage_backend(
    db: Session,
    *,
    size_bytes: int,
    preferred_storage_backend_id: uuid.UUID | None = None,
    exclude_storage_backend_ids: set[uuid.UUID] | frozenset[uuid.UUID] | None = None,
    headroom_ratio: float | None = None,
    require_reachable: bool | None = None,
) -> StorageBackend:
    """Pick a bucket that fits ``size_bytes`` while leaving write headroom.

    Preference order:
      1. The requested ``preferred_storage_backend_id`` if it exists, isn't excluded,
         is reachable (when required), and would stay under ``headroom_ratio``
         after the write.
      2. Otherwise the hottest bucket (per probe-derived ranking) that
         satisfies the headroom constraint.

    Headroom guards against the user write path saturating a bucket, which
    would otherwise force the demote cron to play catch-up.

    When ``require_reachable`` is true (default from
    ``PLACEMENT_REQUIRE_REACHABLE_STORAGE_BACKEND``), buckets without a recent successful
    probe are excluded from new writes.
    """
    effective_excluded = set(exclude_storage_backend_ids or ())
    effective_headroom = (
        headroom_ratio if headroom_ratio is not None else S.STORAGE_WRITE_HEADROOM_RATIO
    )
    effective_require_reachable = (
        S.PLACEMENT_REQUIRE_REACHABLE_STORAGE_BACKEND
        if require_reachable is None
        else require_reachable
    )
    ranked = hotness_ranked_storage_backends(db)
    if effective_require_reachable:
        ranked = [hotness for hotness in ranked if hotness.reachable]
        if not ranked:
            raise ConflictError("No reachable storage backends are configured")
    candidates = [h.storage_backend for h in ranked if h.storage_backend.id not in effective_excluded]
    if not candidates:
        raise ConflictError("No storage backends are configured")

    usages = get_storage_backend_usages(db, [bucket.id for bucket in candidates])

    def fits(bucket: StorageBackend) -> bool:
        usage = usages[bucket.id]
        projected = usage.current_size_bytes + size_bytes
        if projected > bucket.max_size_bytes:
            return False
        if effective_headroom is None or effective_headroom >= 1.0:
            return projected <= bucket.max_size_bytes
        return projected <= int(bucket.max_size_bytes * effective_headroom)

    if preferred_storage_backend_id is not None:
        for bucket in candidates:
            if bucket.id == preferred_storage_backend_id and fits(bucket):
                return bucket

    for bucket in candidates:
        if fits(bucket):
            return bucket

    raise ConflictError("No storage backend has enough capacity")


def agreed_preferred_storage_backend_id(
    db: Session, blob: Blob
) -> uuid.UUID | None:
    """Effective ``preferred_storage_backend_id`` for a (possibly deduplicated) blob.

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
        seen.add(_effective_preferred_storage_backend_id_for_folder(db, folder))

    seen.discard(None)
    if len(seen) == 1:
        return next(iter(seen))
    return None


def _effective_preferred_storage_backend_id_for_folder(
    db: Session, folder: Folder | None
) -> uuid.UUID | None:
    current = folder
    visited: set[uuid.UUID] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        if current.preferred_storage_backend_id is not None:
            return current.preferred_storage_backend_id
        if current.parent_id is None:
            return None
        current = db.get(Folder, current.parent_id)
    return None


def effective_preferred_storage_backend_id(db: Session, folder: Folder) -> uuid.UUID | None:
    """Public form of the folder-chain walk for API serialization."""
    return _effective_preferred_storage_backend_id_for_folder(db, folder)


# ---------------------------------------------------------------------------
# StorageBackend usage cache (unchanged)
# ---------------------------------------------------------------------------


def get_storage_backend_usage(db: Session, storage_backend_id: uuid.UUID) -> StorageBackendUsage:
    return get_storage_backend_usages(db, [storage_backend_id])[storage_backend_id]


def derive_storage_backend_usages(
    db: Session, storage_backend_ids: list[uuid.UUID] | tuple[uuid.UUID, ...] | set[uuid.UUID]
) -> dict[uuid.UUID, StorageBackendUsage]:
    result = {
        storage_backend_id: StorageBackendUsage(object_count=0, current_size_bytes=0)
        for storage_backend_id in storage_backend_ids
    }
    if not result:
        return result

    rows = db.execute(
        select(
            Blob.storage_backend_id,
            func.count(Blob.id),
            func.coalesce(func.sum(Blob.size_bytes), 0),
        )
        .where(Blob.storage_backend_id.in_(list(result)))
        .group_by(Blob.storage_backend_id)
    ).all()
    for storage_backend_id, object_count, size_bytes in rows:
        result[storage_backend_id] = StorageBackendUsage(
            object_count=int(object_count), current_size_bytes=int(size_bytes)
        )
    return result


def get_storage_backend_usages(
    db: Session, storage_backend_ids: list[uuid.UUID] | tuple[uuid.UUID, ...] | set[uuid.UUID]
) -> dict[uuid.UUID, StorageBackendUsage]:
    now = monotonic()
    result: dict[uuid.UUID, StorageBackendUsage] = {}
    missing: list[uuid.UUID] = []

    for storage_backend_id in storage_backend_ids:
        cached = _usage_cache.get(storage_backend_id)
        if cached is not None and cached[0] > now:
            result[storage_backend_id] = cached[1]
        else:
            missing.append(storage_backend_id)

    if missing:
        fresh = derive_storage_backend_usages(db, missing)
        expires_at = now + _USAGE_CACHE_TTL_SECONDS
        for storage_backend_id in missing:
            usage = fresh[storage_backend_id]
            _usage_cache[storage_backend_id] = (expires_at, usage)
            result[storage_backend_id] = usage

    return result


def adjust_storage_backend_usage_cache(
    storage_backend_id: uuid.UUID, *, object_count_delta: int, size_bytes_delta: int
) -> None:
    cached = _usage_cache.get(storage_backend_id)
    if cached is None or cached[0] <= monotonic():
        return

    usage = cached[1]
    _usage_cache[storage_backend_id] = (
        cached[0],
        StorageBackendUsage(
            object_count=max(0, usage.object_count + object_count_delta),
            current_size_bytes=max(0, usage.current_size_bytes + size_bytes_delta),
        ),
    )


def clear_storage_backend_usage_cache(storage_backend_id: uuid.UUID | None = None) -> None:
    if storage_backend_id is None:
        _usage_cache.clear()
        return
    _usage_cache.pop(storage_backend_id, None)


# Imported here to keep mypy happy with forward refs in agreed_preferred_storage_backend_id.
__all__ = [
    "StorageBackendUsage",
    "StorageBackendHotness",
    "hotness_for_storage_backends",
    "hotness_ranked_storage_backends",
    "storage_backend_is_reachable",
    "choose_storage_backend",
    "agreed_preferred_storage_backend_id",
    "effective_preferred_storage_backend_id",
    "get_storage_backend_usage",
    "get_storage_backend_usages",
    "derive_storage_backend_usages",
    "adjust_storage_backend_usage_cache",
    "clear_storage_backend_usage_cache",
]
