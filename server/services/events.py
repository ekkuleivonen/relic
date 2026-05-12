import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from managers.exceptions import BadRequestError
from models import Event

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
SUPPORTED_STATUSES = frozenset({"succeeded", "failed"})


@dataclass(frozen=True)
class EventPage:
    items: list[Event]
    total: int
    limit: int
    offset: int


def create_event(
    db: Session,
    *,
    source: str,
    operation: str,
    status: str,
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    file_ids: list[uuid.UUID | str] | None = None,
    folder_ids: list[uuid.UUID | str] | None = None,
    blob_ids: list[uuid.UUID | str] | None = None,
    metadata: dict | None = None,
) -> Event:
    event = Event(
        source=_clean_required(source, "source"),
        operation=_clean_required(operation, "operation"),
        status=_clean_status(status),
        actor_user_id=actor_user_id,
        request_id=_clean_optional(request_id),
        file_ids=_string_ids(file_ids),
        folder_ids=_string_ids(folder_ids),
        blob_ids=_string_ids(blob_ids),
        meta=dict(metadata or {}),
    )
    db.add(event)
    db.flush()
    return event


def list_events(
    db: Session,
    *,
    source: str | None = None,
    operation: str | None = None,
    status: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> EventPage:
    if limit < 1:
        raise BadRequestError("limit must be >= 1")
    if limit > MAX_LIMIT:
        raise BadRequestError(f"limit must be <= {MAX_LIMIT}")
    if offset < 0:
        raise BadRequestError("offset must be >= 0")

    stmt = _filtered_stmt(
        source=source,
        operation=operation,
        status=status,
        actor_user_id=actor_user_id,
        request_id=request_id,
        created_after=created_after,
        created_before=created_before,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        db.scalars(
            stmt.options(selectinload(Event.actor))
            .order_by(Event.created_at.desc(), Event.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return EventPage(items=items, total=total, limit=limit, offset=offset)


def _filtered_stmt(
    *,
    source: str | None,
    operation: str | None,
    status: str | None,
    actor_user_id: uuid.UUID | None,
    request_id: str | None,
    created_after: dt.datetime | None,
    created_before: dt.datetime | None,
) -> Select[tuple[Event]]:
    stmt = select(Event)
    if source := _clean_optional(source):
        stmt = stmt.where(Event.source == source)
    if operation := _clean_optional(operation):
        stmt = stmt.where(Event.operation == operation)
    if status := _clean_optional(status):
        stmt = stmt.where(Event.status == _clean_status(status))
    if actor_user_id is not None:
        stmt = stmt.where(Event.actor_user_id == actor_user_id)
    if request_id := _clean_optional(request_id):
        stmt = stmt.where(Event.request_id == request_id)
    if created_after is not None:
        stmt = stmt.where(Event.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(Event.created_at < created_before)
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
    if cleaned not in SUPPORTED_STATUSES:
        raise BadRequestError(f"status must be one of {sorted(SUPPORTED_STATUSES)}")
    return cleaned


def _string_ids(values: list[uuid.UUID | str] | None) -> list[str]:
    return [str(value) for value in values or []]
