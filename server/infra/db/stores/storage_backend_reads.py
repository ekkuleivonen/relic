"""StorageBackend catalog reads (usage, probe hotness) — session-level queries."""

import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.exceptions import ResourceNotFound
from infra.db.models import StorageBackend, StorageBackendProbe


@dataclass(frozen=True)
class StorageBackendProbeResult:
    storage_backend: StorageBackend
    probe: StorageBackendProbe
    reachable: bool


def timed_ms(operation) -> int:
    started = time.perf_counter()
    operation()
    return max(1, round((time.perf_counter() - started) * 1000))


from infra.db.stores.placement import (
    StorageBackendHotness,
    StorageBackendUsage,
    derive_storage_backend_usages,
    hotness_for_storage_backends,
)
from utils.secrets import mask_access_key_id, mask_secret_access_key


def list_storage_backends(db: Session) -> list[StorageBackend]:
    return list(db.scalars(select(StorageBackend).order_by(StorageBackend.name)))


def list_storage_backend_reads(db: Session) -> list[dict[str, Any]]:
    buckets = list_storage_backends(db)
    usages = derive_storage_backend_usages(db, [bucket.id for bucket in buckets])
    hotness = hotness_for_storage_backends(db, buckets)
    return [
        storage_backend_read(bucket, usages[bucket.id], hotness[bucket.id])
        for bucket in buckets
    ]


def get_storage_backend(db: Session, storage_backend_id: uuid.UUID) -> StorageBackend:
    bucket = db.get(StorageBackend, storage_backend_id)
    if not bucket:
        raise ResourceNotFound("Storage backend not found")
    return bucket


def get_storage_backend_read(db: Session, storage_backend_id: uuid.UUID) -> dict[str, Any]:
    bucket = get_storage_backend(db, storage_backend_id)
    return storage_backend_read(
        bucket,
        derive_storage_backend_usages(db, [bucket.id])[bucket.id],
        hotness_for_storage_backends(db, [bucket])[bucket.id],
    )


def storage_backend_read(
    bucket: StorageBackend, usage: StorageBackendUsage, hotness: StorageBackendHotness
) -> dict[str, Any]:
    return {
        "id": bucket.id,
        "name": bucket.name,
        "endpoint": bucket.endpoint,
        "region": bucket.region,
        "namespace": bucket.namespace,
        "key_id": mask_access_key_id(bucket.key_id),
        "secret_access_key": mask_secret_access_key(bucket.secret_access_key),
        "max_size_bytes": bucket.max_size_bytes,
        "kind": bucket.kind,
        "object_count": usage.object_count,
        "current_size_bytes": usage.current_size_bytes,
        "avg_latency_ms": (
            round(hotness.avg_latency_ms, 2) if hotness.reachable else None
        ),
        "probe_sample_count": hotness.sample_count,
        "reachable": hotness.reachable,
    }
