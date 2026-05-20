"""Background retention jobs (audit events, stale multipart uploads)."""

import uuid

from application.gateway import object_mutations
from application.uow import UnitOfWork


def trim_old_audit_events(
    uow: UnitOfWork,
    *,
    retention_days: int,
    batch_id: uuid.UUID | None = None,
) -> int:
    effective_batch_id = batch_id or uuid.uuid4()
    deleted_rows = uow.audit.trim_older_than(retention_days=retention_days)
    if deleted_rows > 0:
        uow.audit.emit(
            job="trim_audit_events",
            operation="audit_event.trimmed",
            status="succeeded",
            batch_id=effective_batch_id,
            metadata={
                "retention_days": retention_days,
                "deleted_rows": deleted_rows,
            },
        )
    return deleted_rows


def abort_incomplete_multipart_uploads(
    uow: UnitOfWork,
    *,
    cutoff,
    batch_id: uuid.UUID | None = None,
    abort_after_hours: int,
) -> int:
    effective_batch_id = batch_id or uuid.uuid4()
    deleted_rows = object_mutations.abort_incomplete_uploads_older_than(uow, cutoff)
    if deleted_rows > 0:
        uow.audit.emit(
            job="abort_incomplete_multipart_uploads",
            operation="multipart_upload.aborted",
            status="succeeded",
            batch_id=effective_batch_id,
            metadata={
                "abort_after_hours": abort_after_hours,
                "deleted_rows": deleted_rows,
            },
        )
    return deleted_rows
