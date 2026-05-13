import datetime as dt
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, selectinload

from managers.exceptions import BadRequestError
from models import AuditEvent

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
SUPPORTED_STATUSES = frozenset({"succeeded", "failed"})


@dataclass(frozen=True)
class AuditEventPage:
    items: list[AuditEvent]
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


def create_audit_event(
    db: Session,
    *,
    operation: str,
    status: str = "succeeded",
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    """Write an audit row inside the caller's transaction.

    Audit rows are actor + identity + admin records. Resource-side IDs live
    in ``metadata`` so the table envelope stays narrow — file/folder/blob
    surfacing on event rows is the job of ``file_events`` and
    ``maintenance_events``.
    """
    event = AuditEvent(
        operation=_clean_required(operation, "operation"),
        status=_clean_status(status),
        actor_user_id=actor_user_id,
        request_id=_clean_optional(request_id),
        meta=dict(metadata or {}),
    )
    db.add(event)
    db.flush()
    return event


def record_audit_event(
    db: Session,
    *,
    operation: str,
    status: str = "succeeded",
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = create_audit_event(
        db,
        operation=operation,
        status=status,
        actor_user_id=actor_user_id,
        request_id=request_id,
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
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> AuditEventPage:
    if limit < 1:
        raise BadRequestError("limit must be >= 1")
    if limit > MAX_LIMIT:
        raise BadRequestError(f"limit must be <= {MAX_LIMIT}")
    if offset < 0:
        raise BadRequestError("offset must be >= 0")

    stmt = _filtered_stmt(
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
            stmt.options(selectinload(AuditEvent.actor))
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
    actor_user_id: uuid.UUID | None,
    request_id: str | None,
    created_after: dt.datetime | None,
    created_before: dt.datetime | None,
) -> Select[tuple[AuditEvent]]:
    stmt = select(AuditEvent)
    if operation := _clean_optional(operation):
        stmt = stmt.where(AuditEvent.operation == operation)
    if status := _clean_optional(status):
        stmt = stmt.where(AuditEvent.status == _clean_status(status))
    if actor_user_id is not None:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
    if request_id := _clean_optional(request_id):
        stmt = stmt.where(AuditEvent.request_id == request_id)
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
    if cleaned not in SUPPORTED_STATUSES:
        raise BadRequestError(f"status must be one of {sorted(SUPPORTED_STATUSES)}")
    return cleaned
