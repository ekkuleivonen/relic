import uuid
from typing import Any

from application.context import EventContext
from infra.db.stores.storage_backend_probe import probe_storage_backend as run_storage_backend_probe
from infra.db.stores.storage_backend_reads import StorageBackendProbeResult
from infra.db.stores.placement import clear_storage_backend_usage_cache
from application.uow import UnitOfWork
from domain.exceptions import ConflictError
from ports.entities import StorageBackend
from utils.logging import get_logger
from utils.timing import elapsed_ms, latency_metadata, timer_start

log = get_logger(__name__)


def create_storage_backend(
    uow: UnitOfWork,
    values: dict[str, Any],
    *,
    event_context: EventContext | None = None,
) -> StorageBackend:
    started_at = timer_start()
    db_started = timer_start()
    uow.storage_backends.ensure_name_available(values["name"])
    bucket = StorageBackend(**values)
    uow.storage_backends.add(bucket)
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    uow.audit.record(
        operation="storage_backend.created",
        event_context=event_context,
        metadata={
            "storage_backend_id": str(bucket.id),
            "name": bucket.name,
            **latency_metadata(started_at, db_latency_ms=db_latency_ms),
        },
        db_latency_ms=db_latency_ms,
    )
    log.info("storage_backend_create", storage_backend_id=str(bucket.id), name=bucket.name)
    return bucket


def update_storage_backend(
    uow: UnitOfWork,
    storage_backend_id: uuid.UUID,
    values: dict[str, Any],
    *,
    event_context: EventContext | None = None,
) -> StorageBackend:
    started_at = timer_start()
    db_started = timer_start()
    bucket = uow.storage_backends.get(storage_backend_id)
    if "name" in values:
        uow.storage_backends.ensure_name_available(values["name"], excluding_id=bucket.id)
    uow.storage_backends.apply_updates(bucket, values)
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    uow.audit.record(
        operation="storage_backend.updated",
        event_context=event_context,
        metadata={
            "storage_backend_id": str(bucket.id),
            "name": bucket.name,
            "changed_fields": sorted(values),
            **latency_metadata(started_at, db_latency_ms=db_latency_ms),
        },
        db_latency_ms=db_latency_ms,
    )
    log.info("storage_backend_update", storage_backend_id=str(bucket.id), name=bucket.name)
    return bucket


def delete_storage_backend(
    uow: UnitOfWork,
    storage_backend_id: uuid.UUID,
    *,
    event_context: EventContext | None = None,
) -> None:
    started_at = timer_start()
    db_started = timer_start()
    bucket = uow.storage_backends.get(storage_backend_id)
    blob_count = uow.storage_backends.blob_count(bucket.id)
    if blob_count:
        raise ConflictError(
            "Storage backend still has blobs",
            detail={"message": "Storage backend still has blobs", "blob_count": blob_count},
        )

    metadata = {"storage_backend_id": str(bucket.id), "name": bucket.name}
    uow.storage_backends.delete(bucket)
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    uow.audit.record(
        operation="storage_backend.deleted",
        event_context=event_context,
        metadata={
            **metadata,
            **latency_metadata(started_at, db_latency_ms=db_latency_ms),
        },
        db_latency_ms=db_latency_ms,
    )
    clear_storage_backend_usage_cache(bucket.id)
    log.info("storage_backend_delete", storage_backend_id=str(bucket.id), name=bucket.name)


def probe_storage_backend(uow: UnitOfWork, storage_backend_id: uuid.UUID) -> StorageBackendProbeResult:
    return run_storage_backend_probe(uow, storage_backend_id)
