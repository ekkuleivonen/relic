import datetime as dt
import uuid
from dataclasses import dataclass

from domain.exceptions import BadRequestError
from domain.file_events.types import FILE_EVENT_TYPES
from enums import UserRole
from infra.db.models import FileEvent, User
from infra.db.stores import folder_access
from infra.db.stores.search_scope import scope_folder_ids_for_events
from sqlalchemy import func, select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class FileEventPage:
    items: list[FileEvent]
    cursor: int | None
    has_more: bool
    oldest_seq: int | None


def create_file_event(
    db: Session,
    *,
    event_type: str,
    file_id: uuid.UUID,
    folder_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    request_id: str | None,
    payload: dict,
) -> FileEvent:
    if event_type not in FILE_EVENT_TYPES:
        raise BadRequestError(f"Unsupported file event type: {event_type}")

    next_seq = (db.scalar(select(func.coalesce(func.max(FileEvent.seq), 0))) or 0) + 1
    event = FileEvent(
        seq=next_seq,
        event_type=event_type,
        file_id=file_id,
        folder_id=folder_id,
        actor_id=actor_id,
        request_id=request_id,
        payload=dict(payload),
    )
    db.add(event)
    db.flush()
    return event


def oldest_file_event_seq(db: Session) -> int | None:
    return db.scalar(select(func.min(FileEvent.seq)))


def list_file_events(
    db: Session,
    user: User,
    *,
    after: int,
    folder_id: uuid.UUID | None,
    recursive: bool,
    event_types: frozenset[str] | None,
    limit: int,
) -> FileEventPage:
    if after < 0:
        raise BadRequestError("after must be >= 0")
    if limit < 1:
        raise BadRequestError("limit must be >= 1")

    stmt = select(FileEvent).where(FileEvent.seq > after)

    if user.role != UserRole.ADMIN:
        visible_ids = folder_access.visible_folder_ids(db, user)
        if not visible_ids:
            return FileEventPage(
                items=[],
                cursor=after if after > 0 else None,
                has_more=False,
                oldest_seq=oldest_file_event_seq(db),
            )
        stmt = stmt.where(FileEvent.folder_id.in_(visible_ids))

    if folder_id is not None:
        scoped_ids = scope_folder_ids_for_events(
            db,
            user=user,
            folder_id=folder_id,
            recursive=recursive,
        )
        if not scoped_ids:
            return FileEventPage(
                items=[],
                cursor=after if after > 0 else None,
                has_more=False,
                oldest_seq=oldest_file_event_seq(db),
            )
        stmt = stmt.where(FileEvent.folder_id.in_(scoped_ids))

    if event_types:
        unknown = event_types - FILE_EVENT_TYPES
        if unknown:
            raise BadRequestError(
                f"Unsupported file event types: {sorted(unknown)}"
            )
        stmt = stmt.where(FileEvent.event_type.in_(event_types))

    stmt = stmt.order_by(FileEvent.seq.asc()).limit(limit + 1)
    rows = list(db.scalars(stmt).all())
    has_more = len(rows) > limit
    items = rows[:limit]
    cursor = items[-1].seq if items else (after if after > 0 else None)
    return FileEventPage(
        items=items,
        cursor=cursor,
        has_more=has_more,
        oldest_seq=oldest_file_event_seq(db),
    )


def trim_file_events_older_than(
    db: Session,
    *,
    retention_days: int,
    now: dt.datetime | None = None,
) -> int:
    effective_now = now or dt.datetime.now(dt.UTC)
    cutoff = effective_now - dt.timedelta(days=retention_days)
    from sqlalchemy import delete

    result = db.execute(delete(FileEvent).where(FileEvent.created_at < cutoff))
    return result.rowcount or 0
