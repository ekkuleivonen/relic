import datetime as dt
import time
import uuid
from dataclasses import dataclass

from starlette.datastructures import Headers
from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, selectinload

from managers.exceptions import BadRequestError
from models import Event

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
SUPPORTED_STATUSES = frozenset({"succeeded", "failed"})


@dataclass(frozen=True)
class EventContext:
    source: str
    actor_user_id: uuid.UUID | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class EventPage:
    items: list[Event]
    total: int
    limit: int
    offset: int


def timer_start() -> float:
    return time.perf_counter()


def elapsed_ms(started_at: float, *, minimum: int = 1) -> int:
    return max(minimum, round((time.perf_counter() - started_at) * 1000))


def latency_metadata(
    started_at: float,
    *,
    db_latency_ms: int | None = None,
    remote_latency_ms: int | None = None,
) -> dict[str, int]:
    metadata = {"duration_ms": elapsed_ms(started_at)}
    if db_latency_ms is not None:
        metadata["db_latency_ms"] = db_latency_ms
    if remote_latency_ms is not None:
        metadata["remote_latency_ms"] = remote_latency_ms
    return metadata


def create_event(
    db: Session,
    *,
    source: str,
    operation: str,
    status: str = "succeeded",
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


def record_event(
    db: Session,
    *,
    source: str,
    operation: str,
    status: str = "succeeded",
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    file_ids: list[uuid.UUID | str] | None = None,
    folder_ids: list[uuid.UUID | str] | None = None,
    blob_ids: list[uuid.UUID | str] | None = None,
    metadata: dict | None = None,
) -> Event:
    event = create_event(
        db,
        source=source,
        operation=operation,
        status=status,
        actor_user_id=actor_user_id,
        request_id=request_id,
        file_ids=file_ids,
        folder_ids=folder_ids,
        blob_ids=blob_ids,
        metadata=metadata,
    )
    db.commit()
    db.refresh(event)
    return event


def clear_events(db: Session) -> int:
    result = db.execute(delete(Event))
    db.commit()
    return result.rowcount or 0


def context_from_headers(
    headers: Headers,
    *,
    source: str,
    actor_user_id: uuid.UUID | None = None,
) -> EventContext:
    return EventContext(
        source=source,
        actor_user_id=actor_user_id,
        request_id=request_id_from_headers(headers),
    )


def request_id_from_headers(headers: Headers) -> str | None:
    return headers.get("x-request-id") or headers.get("x-correlation-id")


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
