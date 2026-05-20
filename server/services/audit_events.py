import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, selectinload

from constants import AUDIT_EVENT_DEFAULT_LIMIT, AUDIT_EVENT_MAX_LIMIT
from domain.exceptions import BadRequestError
from enums import EventStatus
from models import AuditEvent

AUDIT_EVENT_SUPPORTED_STATUSES = frozenset(status.value for status in EventStatus)


@dataclass(frozen=True)
class AuditEventPage:
    items: list[AuditEvent]
    total: int
    limit: int
    offset: int


def create_audit_event(
    db: Session,
    *,
    operation: str,
    status: str = EventStatus.SUCCEEDED.value,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
    job: str | None = None,
    batch_id: uuid.UUID | None = None,
    bucket_id: uuid.UUID | None = None,
    blob_id: uuid.UUID | None = None,
    duration_ms: int | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        operation=_clean_required(operation, "operation"),
        status=_clean_status(status),
        actor_id=actor_id,
        request_id=_clean_optional(request_id),
        job=_clean_optional(job),
        batch_id=batch_id,
        bucket_id=bucket_id,
        blob_id=blob_id,
        duration_ms=duration_ms,
        meta=dict(metadata or {}),
    )
    db.add(event)
    db.flush()
    return event


def record_audit_event(
    db: Session,
    *,
    operation: str,
    status: str = EventStatus.SUCCEEDED.value,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
    job: str | None = None,
    batch_id: uuid.UUID | None = None,
    bucket_id: uuid.UUID | None = None,
    blob_id: uuid.UUID | None = None,
    duration_ms: int | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = create_audit_event(
        db,
        operation=operation,
        status=status,
        actor_id=actor_id,
        request_id=request_id,
        job=job,
        batch_id=batch_id,
        bucket_id=bucket_id,
        blob_id=blob_id,
        duration_ms=duration_ms,
        metadata=metadata,
    )
    db.commit()
    db.refresh(event)
    return event


def clear_audit_events(db: Session) -> int:
    result = db.execute(delete(AuditEvent))
    db.commit()
    return result.rowcount or 0


def trim_audit_events_older_than(
    db: Session,
    *,
    retention_days: int,
    now: dt.datetime | None = None,
) -> int:
    effective_now = now or dt.datetime.now(dt.UTC)
    cutoff = effective_now - dt.timedelta(days=retention_days)
    result = db.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff))
    db.commit()
    return result.rowcount or 0


def list_audit_events(
    db: Session,
    *,
    operation: str | None = None,
    status: str | None = None,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
    job: str | None = None,
    batch_id: uuid.UUID | None = None,
    bucket_id: uuid.UUID | None = None,
    blob_id: uuid.UUID | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = AUDIT_EVENT_DEFAULT_LIMIT,
    offset: int = 0,
) -> AuditEventPage:
    if limit < 1:
        raise BadRequestError("limit must be >= 1")
    if limit > AUDIT_EVENT_MAX_LIMIT:
        raise BadRequestError(f"limit must be <= {AUDIT_EVENT_MAX_LIMIT}")
    if offset < 0:
        raise BadRequestError("offset must be >= 0")

    stmt = _filtered_stmt(
        operation=operation,
        status=status,
        actor_id=actor_id,
        request_id=request_id,
        job=job,
        batch_id=batch_id,
        bucket_id=bucket_id,
        blob_id=blob_id,
        created_after=created_after,
        created_before=created_before,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        db.scalars(
            stmt.options(
                selectinload(AuditEvent.actor),
                selectinload(AuditEvent.bucket),
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return AuditEventPage(items=items, total=total, limit=limit, offset=offset)


def _filtered_stmt(
    *,
    operation: str | None,
    status: str | None,
    actor_id: uuid.UUID | None,
    request_id: str | None,
    job: str | None,
    batch_id: uuid.UUID | None,
    bucket_id: uuid.UUID | None,
    blob_id: uuid.UUID | None,
    created_after: dt.datetime | None,
    created_before: dt.datetime | None,
) -> Select[tuple[AuditEvent]]:
    stmt = select(AuditEvent)
    if operation := _clean_optional(operation):
        stmt = stmt.where(AuditEvent.operation == operation)
    if status := _clean_optional(status):
        stmt = stmt.where(AuditEvent.status == _clean_status(status))
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if request_id := _clean_optional(request_id):
        stmt = stmt.where(AuditEvent.request_id == request_id)
    if job := _clean_optional(job):
        stmt = stmt.where(AuditEvent.job == job)
    if batch_id is not None:
        stmt = stmt.where(AuditEvent.batch_id == batch_id)
    if bucket_id is not None:
        stmt = stmt.where(AuditEvent.bucket_id == bucket_id)
    if blob_id is not None:
        stmt = stmt.where(AuditEvent.blob_id == blob_id)
    if created_after is not None:
        stmt = stmt.where(AuditEvent.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(AuditEvent.created_at < created_before)
    return stmt


def _clean_required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise BadRequestError(f"{field} cannot be empty")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_status(value: str) -> str:
    cleaned = _clean_required(value, "status")
    if cleaned not in AUDIT_EVENT_SUPPORTED_STATUSES:
        raise BadRequestError(
            f"status must be one of {sorted(AUDIT_EVENT_SUPPORTED_STATUSES)}"
        )
    return cleaned
