import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, selectinload

from constants import (
    MAINTENANCE_EVENT_DEFAULT_LIMIT,
    MAINTENANCE_EVENT_MAX_LIMIT,
)
from domain.exceptions import BadRequestError
from enums import EventStatus
from models import MaintenanceEvent

MAINTENANCE_EVENT_SUPPORTED_STATUSES = frozenset(status.value for status in EventStatus)

@dataclass(frozen=True)
class MaintenanceEventPage:
    items: list[MaintenanceEvent]
    total: int
    limit: int
    offset: int


def create_maintenance_event(
    db: Session,
    *,
    job: str,
    action: str,
    status: str,
    batch_id: uuid.UUID,
    bucket_id: uuid.UUID | None = None,
    blob_id: uuid.UUID | None = None,
    duration_ms: int | None = None,
    metadata: dict | None = None,
) -> MaintenanceEvent:
    event = MaintenanceEvent(
        job=_clean_required(job, "job"),
        action=_clean_required(action, "action"),
        status=_clean_status(status),
        batch_id=batch_id,
        bucket_id=bucket_id,
        blob_id=blob_id,
        duration_ms=duration_ms,
        meta=dict(metadata or {}),
    )
    db.add(event)
    db.flush()
    return event


def clear_maintenance_events(db: Session) -> int:
    result = db.execute(delete(MaintenanceEvent))
    db.commit()
    return result.rowcount or 0


def trim_maintenance_events_older_than(
    db: Session,
    *,
    retention_days: int,
    now: dt.datetime | None = None,
) -> int:
    effective_now = now or dt.datetime.now(dt.UTC)
    cutoff = effective_now - dt.timedelta(days=retention_days)
    result = db.execute(
        delete(MaintenanceEvent).where(MaintenanceEvent.created_at < cutoff)
    )
    db.commit()
    return result.rowcount or 0


def list_maintenance_events(
    db: Session,
    *,
    job: str | None = None,
    action: str | None = None,
    status: str | None = None,
    batch_id: uuid.UUID | None = None,
    bucket_id: uuid.UUID | None = None,
    blob_id: uuid.UUID | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = MAINTENANCE_EVENT_DEFAULT_LIMIT,
    offset: int = 0,
) -> MaintenanceEventPage:
    if limit < 1:
        raise BadRequestError("limit must be >= 1")
    if limit > MAINTENANCE_EVENT_MAX_LIMIT:
        raise BadRequestError(f"limit must be <= {MAINTENANCE_EVENT_MAX_LIMIT}")
    if offset < 0:
        raise BadRequestError("offset must be >= 0")

    stmt = _filtered_stmt(
        job=job,
        action=action,
        status=status,
        batch_id=batch_id,
        bucket_id=bucket_id,
        blob_id=blob_id,
        created_after=created_after,
        created_before=created_before,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        db.scalars(
            stmt.options(selectinload(MaintenanceEvent.bucket))
            .order_by(MaintenanceEvent.created_at.desc(), MaintenanceEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return MaintenanceEventPage(items=items, total=total, limit=limit, offset=offset)


def _filtered_stmt(
    *,
    job: str | None,
    action: str | None,
    status: str | None,
    batch_id: uuid.UUID | None,
    bucket_id: uuid.UUID | None,
    blob_id: uuid.UUID | None,
    created_after: dt.datetime | None,
    created_before: dt.datetime | None,
) -> Select[tuple[MaintenanceEvent]]:
    stmt = select(MaintenanceEvent)
    if job := _clean_optional(job):
        stmt = stmt.where(MaintenanceEvent.job == job)
    if action := _clean_optional(action):
        stmt = stmt.where(MaintenanceEvent.action == action)
    if status := _clean_optional(status):
        stmt = stmt.where(MaintenanceEvent.status == _clean_status(status))
    if batch_id is not None:
        stmt = stmt.where(MaintenanceEvent.batch_id == batch_id)
    if bucket_id is not None:
        stmt = stmt.where(MaintenanceEvent.bucket_id == bucket_id)
    if blob_id is not None:
        stmt = stmt.where(MaintenanceEvent.blob_id == blob_id)
    if created_after is not None:
        stmt = stmt.where(MaintenanceEvent.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(MaintenanceEvent.created_at < created_before)
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
    if cleaned not in MAINTENANCE_EVENT_SUPPORTED_STATUSES:
        raise BadRequestError(
            f"status must be one of {sorted(MAINTENANCE_EVENT_SUPPORTED_STATUSES)}"
        )
    return cleaned
