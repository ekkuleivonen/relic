import uuid

from application.context import EventContext
from infra.maintenance.storage import drain_storage_backend_batch
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError

import settings as S


def drain_storage_backend(
    uow: UnitOfWork,
    *,
    storage_backend_id: uuid.UUID,
    event_context: EventContext | None = None,
) -> dict:
    bucket = uow.storage_backends.get(storage_backend_id)
    blob_count = uow.storage_backends.blob_count(bucket.id)
    if blob_count == 0:
        return {"moved": 0, "skipped": 0, "failed": 0, "scanned": 0}

    uow.audit.record(
        operation="storage_backend.drain_started",
        event_context=event_context,
        metadata={"storage_backend_id": str(bucket.id), "blob_count": blob_count},
    )

    result = drain_storage_backend_batch(
        uow,
        storage_backend_id=storage_backend_id,
        demote_limit=blob_count,
        headroom_ratio=S.STORAGE_PROMOTION_HEADROOM_RATIO,
        min_residency_hours=0,
    )

    remaining = uow.storage_backends.blob_count(bucket.id)
    if remaining > 0:
        raise BadRequestError(
            "StorageBackend drain incomplete",
            detail={"remaining_blobs": remaining, **result},
        )

    uow.audit.record(
        operation="storage_backend.drained",
        event_context=event_context,
        metadata={"storage_backend_id": str(bucket.id), **result},
    )
    return result
