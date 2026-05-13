import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, delete, func, select, text
from sqlalchemy.orm import Session, selectinload

from constants import (
    FILE_EVENT_CHANNEL,
    FILE_EVENT_DEFAULT_LIMIT,
    FILE_EVENT_MAX_LIMIT,
)
from domain.exceptions import BadRequestError
from enums import EventStatus
from models import FileEvent, Processor

FILE_EVENT_SUPPORTED_STATUSES = frozenset(
    {EventStatus.SUCCEEDED.value, EventStatus.FAILED.value}
)

@dataclass(frozen=True)
class FileEventPage:
    items: list[FileEvent]
    total: int
    limit: int
    offset: int


def create_file_event(
    db: Session,
    *,
    event_type: str,
    status: str = EventStatus.SUCCEEDED.value,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    file_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> FileEvent:
    event = FileEvent(
        event_type=_clean_required(event_type, "event_type"),
        status=_clean_status(status),
        actor_id=actor_id,
        request_id=_clean_optional(request_id),
        idempotency_key=_clean_optional(idempotency_key),
        file_id=file_id,
        folder_id=folder_id,
        payload=dict(payload or {}),
    )
    _assign_sqlite_offset(db, event)
    db.add(event)
    db.flush()
    _notify_file_event(db, event)
    return event


def trim_file_events_older_than(
    db: Session,
    *,
    retention_days: int,
    now: dt.datetime | None = None,
) -> int:
    effective_now = now or dt.datetime.now(dt.UTC)
    cutoff = effective_now - dt.timedelta(days=retention_days)
    safe_offset = _safe_trim_offset(db)
    result = db.execute(
        delete(FileEvent).where(
            FileEvent.created_at < cutoff,
            FileEvent.offset <= safe_offset,
        )
    )
    db.commit()
    return result.rowcount or 0


def clear_file_events(db: Session) -> int:
    safe_offset = _safe_trim_offset(db)
    head_offset = db.scalar(select(func.coalesce(func.max(FileEvent.offset), 0))) or 0
    if int(head_offset) > safe_offset:
        raise BadRequestError(
            "Cannot clear file events while enabled processors have pending events"
        )
    result = db.execute(delete(FileEvent))
    db.commit()
    return result.rowcount or 0


def list_file_events(
    db: Session,
    *,
    event_type: str | None = None,
    status: str | None = None,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
    file_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = FILE_EVENT_DEFAULT_LIMIT,
    offset: int = 0,
) -> FileEventPage:
    if limit < 1:
        raise BadRequestError("limit must be >= 1")
    if limit > FILE_EVENT_MAX_LIMIT:
        raise BadRequestError(f"limit must be <= {FILE_EVENT_MAX_LIMIT}")
    if offset < 0:
        raise BadRequestError("offset must be >= 0")

    stmt = _filtered_stmt(
        event_type=event_type,
        status=status,
        actor_id=actor_id,
        request_id=request_id,
        file_id=file_id,
        folder_id=folder_id,
        created_after=created_after,
        created_before=created_before,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        db.scalars(
            stmt.options(selectinload(FileEvent.actor))
            .order_by(FileEvent.offset.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return FileEventPage(items=items, total=total, limit=limit, offset=offset)


def _filtered_stmt(
    *,
    event_type: str | None,
    status: str | None,
    actor_id: uuid.UUID | None,
    request_id: str | None,
    file_id: uuid.UUID | None,
    folder_id: uuid.UUID | None,
    created_after: dt.datetime | None,
    created_before: dt.datetime | None,
) -> Select[tuple[FileEvent]]:
    stmt = select(FileEvent)
    if event_type := _clean_optional(event_type):
        stmt = stmt.where(FileEvent.event_type == event_type)
    if status := _clean_optional(status):
        stmt = stmt.where(FileEvent.status == _clean_status(status))
    if actor_id is not None:
        stmt = stmt.where(FileEvent.actor_id == actor_id)
    if request_id := _clean_optional(request_id):
        stmt = stmt.where(FileEvent.request_id == request_id)
    if file_id is not None:
        stmt = stmt.where(FileEvent.file_id == file_id)
    if folder_id is not None:
        stmt = stmt.where(FileEvent.folder_id == folder_id)
    if created_after is not None:
        stmt = stmt.where(FileEvent.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(FileEvent.created_at < created_before)
    return stmt


def _assign_sqlite_offset(db: Session, event: FileEvent) -> None:
    if db.get_bind().dialect.name != "sqlite":
        return
    max_offset = db.scalar(select(func.max(FileEvent.offset))) or 0
    event.offset = max_offset + 1


def _notify_file_event(db: Session, event: FileEvent) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": FILE_EVENT_CHANNEL, "payload": str(event.id)},
    )


def _safe_trim_offset(db: Session) -> int:
    slowest_enabled_cursor = db.scalar(
        select(func.min(Processor.last_committed_offset)).where(
            Processor.enabled.is_(True)
        )
    )
    if slowest_enabled_cursor is None:
        return int(db.scalar(select(func.coalesce(func.max(FileEvent.offset), 0))) or 0)
    return int(slowest_enabled_cursor)


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
    if cleaned not in FILE_EVENT_SUPPORTED_STATUSES:
        raise BadRequestError(
            f"status must be one of {sorted(FILE_EVENT_SUPPORTED_STATUSES)}"
        )
    return cleaned
