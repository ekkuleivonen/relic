import uuid

from application.context import EventContext
from infra.maintenance.storage import drain_bucket_batch
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError

import settings as S


def drain_bucket(
    uow: UnitOfWork,
    *,
    bucket_id: uuid.UUID,
    event_context: EventContext | None = None,
) -> dict:
    bucket = uow.buckets.get(bucket_id)
    blob_count = uow.buckets.blob_count(bucket.id)
    if blob_count == 0:
        return {"moved": 0, "skipped": 0, "failed": 0, "scanned": 0}

    uow.audit.record(
        operation="bucket.drain_started",
        event_context=event_context,
        metadata={"bucket_id": str(bucket.id), "blob_count": blob_count},
    )

    result = drain_bucket_batch(
        uow,
        bucket_id=bucket_id,
        demote_limit=blob_count,
        headroom_ratio=S.STORAGE_PROMOTION_HEADROOM_RATIO,
        min_residency_hours=0,
    )

    remaining = uow.buckets.blob_count(bucket.id)
    if remaining > 0:
        raise BadRequestError(
            "Bucket drain incomplete",
            detail={"remaining_blobs": remaining, **result},
        )

    uow.audit.record(
        operation="bucket.drained",
        event_context=event_context,
        metadata={"bucket_id": str(bucket.id), **result},
    )
    return result
