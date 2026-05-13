"""Processor lifecycle, dispatch, and execution.

This module owns:
  * CRUD for the `processors` table (admin-managed and seeded rows).
  * The pull-based dispatcher query that surfaces undispatched events for
    each enabled processor.
  * The transactional worker handler that runs a substrate, emits the
    `processor.<kind>.{completed,failed}` outcome event, and advances the
    durable cursor on success.
  * Operator actions (rewind, skip-stuck, enable/disable) that touch the
    cursor and write a corresponding `audit_events` row.

See `ROADMAP.md` for the architectural contract: handlers must be idempotent
over `event_id`, per-processor concurrency is 1 (enforced by `SELECT ... FOR
UPDATE` on the processor row), and the cursor only advances on success.
"""

import datetime as dt
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from constants import (
    PROCESSOR_DEFAULT_DISPATCH_BATCH,
    PROCESSOR_DEFAULT_LIST_LIMIT,
    PROCESSOR_MAX_LIST_LIMIT,
    PROCESSOR_MAX_REWIND_OFFSET,
    PROCESSOR_SOURCE_ADMIN,
    PROCESSOR_SOURCE_SEED,
)
from domain.exceptions import BadRequestError, ConflictError, ResourceNotFound
from models import (
    FileEvent,
    Folder,
    Processor,
)
from processors.registry import (
    ProcessorContext,
    get_substrate,
    list_substrate_kinds,
    validate_config,
    validate_subscribed_event_types,
)
from services import audit_events as audit_event_service
from services.event_context import EventContext
from services.file_events import create_file_event
from services.filesystem import collect_descendant_folder_ids
from utils.logging import get_logger

log = get_logger(__name__)

@dataclass(frozen=True)
class ProcessorWithLag:
    processor: Processor
    pending_count: int
    head_offset: int


@dataclass(frozen=True)
class ProcessorPage:
    items: list[ProcessorWithLag]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class PendingDispatchJob:
    processor_id: uuid.UUID
    event_id: uuid.UUID
    event_offset: int
    event_type: str


@dataclass(frozen=True)
class ExecutionResult:
    """What the worker handler reports back for logging/metrics."""

    status: str  # 'ok' | 'failed' | 'skipped_disabled' | 'skipped_missing_processor' | 'skipped_already_processed' | 'skipped_missing_event'
    advanced_to_offset: int | None
    duration_ms: int


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_processor(
    db: Session,
    *,
    name: str,
    kind: str,
    subscribed_event_types: list[str] | None = None,
    folder_scopes: list[dict] | None = None,
    config: dict | None = None,
    enabled: bool = True,
    source: str = PROCESSOR_SOURCE_ADMIN,
    event_context: EventContext | None = None,
) -> Processor:
    cleaned_name = _clean_required(name, "name")
    cleaned_kind = _clean_required(kind, "kind")
    substrate = get_substrate(cleaned_kind)
    types = (
        validate_subscribed_event_types(
            kind=cleaned_kind, event_types=subscribed_event_types
        )
        if subscribed_event_types is not None
        else list(substrate.default_subscribed_event_types)
    )

    cleaned_config = validate_config(kind=cleaned_kind, config=config)
    cleaned_folder_scopes = _validate_folder_scopes(db, folder_scopes)
    processor = Processor(
        name=cleaned_name,
        kind=cleaned_kind,
        enabled=enabled,
        source=source,
        subscribed_event_types=types,
        folder_scopes=cleaned_folder_scopes,
        config=cleaned_config,
        last_committed_offset=0,
    )
    db.add(processor)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Processor with name {cleaned_name!r} already exists"
        ) from exc

    if event_context is not None:
        audit_event_service.create_audit_event(
            db,
            operation="processor.created",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            metadata={
                "processor_id": str(processor.id),
                "name": processor.name,
                "kind": processor.kind,
                "source": processor.source,
                "subscribed_event_types": processor.subscribed_event_types,
                "folder_scopes": processor.folder_scopes,
            },
        )
    db.commit()
    db.refresh(processor)
    return processor


def upsert_seed_processor(
    db: Session,
    *,
    name: str,
    kind: str,
    subscribed_event_types: list[str] | None = None,
    folder_scopes: list[dict] | None = None,
    config: dict | None = None,
) -> Processor:
    """Idempotent seed entrypoint. Preserves cursor + enabled state on re-run."""
    existing = db.scalar(select(Processor).where(Processor.name == name))
    if existing is not None:
        existing.kind = kind
        existing.source = PROCESSOR_SOURCE_SEED
        if subscribed_event_types is not None:
            existing.subscribed_event_types = list(subscribed_event_types)
        if folder_scopes is not None:
            existing.folder_scopes = _validate_folder_scopes(db, folder_scopes)
        if config is not None:
            existing.config = validate_config(kind=kind, config=config)
        return existing
    return create_processor(
        db,
        name=name,
        kind=kind,
        subscribed_event_types=subscribed_event_types,
        folder_scopes=folder_scopes,
        config=config,
        enabled=True,
        source=PROCESSOR_SOURCE_SEED,
        event_context=None,
    )


def update_processor(
    db: Session,
    *,
    processor_id: uuid.UUID,
    enabled: bool | None = None,
    subscribed_event_types: list[str] | None = None,
    folder_scopes: list[dict] | None = None,
    config: dict | None = None,
    event_context: EventContext | None = None,
) -> Processor:
    processor = require_processor(db, processor_id)
    if processor.source == PROCESSOR_SOURCE_SEED and (
        subscribed_event_types is not None
        or folder_scopes is not None
        or config is not None
    ):
        raise BadRequestError(
            "Seeded processors only allow enabled state and cursor changes"
        )

    changes: dict[str, dict] = {}
    if enabled is not None and enabled != processor.enabled:
        changes["enabled"] = {"from": processor.enabled, "to": enabled}
        processor.enabled = enabled
    if subscribed_event_types is not None:
        cleaned = validate_subscribed_event_types(
            kind=processor.kind, event_types=subscribed_event_types
        )
        if cleaned != processor.subscribed_event_types:
            changes["subscribed_event_types"] = {
                "from": list(processor.subscribed_event_types),
                "to": cleaned,
            }
            processor.subscribed_event_types = cleaned
    if folder_scopes is not None:
        cleaned_folder_scopes = _validate_folder_scopes(db, folder_scopes)
        if cleaned_folder_scopes != processor.folder_scopes:
            changes["folder_scopes"] = {
                "from": list(processor.folder_scopes),
                "to": cleaned_folder_scopes,
            }
            processor.folder_scopes = cleaned_folder_scopes
    if config is not None:
        cleaned_config = validate_config(kind=processor.kind, config=config)
        if cleaned_config != processor.config:
            changes["config"] = {
                "from": dict(processor.config),
                "to": dict(cleaned_config),
            }
            processor.config = cleaned_config

    if not changes:
        return processor

    db.flush()
    if event_context is not None:
        operation = "processor.updated"
        if set(changes) == {"enabled"}:
            operation = (
                "processor.enabled" if processor.enabled else "processor.disabled"
            )
        audit_event_service.create_audit_event(
            db,
            operation=operation,
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            metadata={
                "processor_id": str(processor.id),
                "name": processor.name,
                "changes": changes,
            },
        )
    db.commit()
    db.refresh(processor)
    return processor


def delete_processor(
    db: Session,
    *,
    processor_id: uuid.UUID,
    event_context: EventContext | None = None,
) -> None:
    processor = require_processor(db, processor_id)
    if processor.source == PROCESSOR_SOURCE_SEED:
        raise BadRequestError("Seeded processors cannot be deleted")

    snapshot = {
        "processor_id": str(processor.id),
        "name": processor.name,
        "kind": processor.kind,
    }
    db.delete(processor)
    db.flush()
    if event_context is not None:
        audit_event_service.create_audit_event(
            db,
            operation="processor.deleted",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            metadata=snapshot,
        )
    db.commit()


def require_processor(db: Session, processor_id: uuid.UUID) -> Processor:
    processor = db.get(Processor, processor_id)
    if processor is None:
        raise ResourceNotFound("Processor not found")
    return processor


# ---------------------------------------------------------------------------
# Listing + lag
# ---------------------------------------------------------------------------


def list_processors(
    db: Session,
    *,
    limit: int = PROCESSOR_DEFAULT_LIST_LIMIT,
    offset: int = 0,
) -> ProcessorPage:
    if limit < 1:
        raise BadRequestError("limit must be >= 1")
    if limit > PROCESSOR_MAX_LIST_LIMIT:
        raise BadRequestError(f"limit must be <= {PROCESSOR_MAX_LIST_LIMIT}")
    if offset < 0:
        raise BadRequestError("offset must be >= 0")

    total = db.scalar(select(func.count()).select_from(Processor)) or 0
    rows = list(
        db.scalars(
            select(Processor)
            .order_by(Processor.name.asc())
            .limit(limit)
            .offset(offset)
        )
    )
    head_offset = db.scalar(select(func.coalesce(func.max(FileEvent.offset), 0))) or 0
    items = [
        ProcessorWithLag(
            processor=processor,
            pending_count=_pending_count(db, processor),
            head_offset=int(head_offset),
        )
        for processor in rows
    ]
    return ProcessorPage(items=items, total=total, limit=limit, offset=offset)


def get_processor_with_lag(db: Session, processor_id: uuid.UUID) -> ProcessorWithLag:
    processor = require_processor(db, processor_id)
    head_offset = db.scalar(select(func.coalesce(func.max(FileEvent.offset), 0))) or 0
    return ProcessorWithLag(
        processor=processor,
        pending_count=_pending_count(db, processor),
        head_offset=int(head_offset),
    )


def _pending_count(db: Session, processor: Processor) -> int:
    if not processor.subscribed_event_types:
        return 0
    stmt = _matching_events_stmt(db, processor).with_only_columns(func.count())
    return int(
        db.scalar(stmt)
        or 0
    )


# ---------------------------------------------------------------------------
# Dispatcher: surface events the worker should pick up next.
# ---------------------------------------------------------------------------


def collect_pending_jobs(
    db: Session,
    *,
    batch_size: int = PROCESSOR_DEFAULT_DISPATCH_BATCH,
) -> list[PendingDispatchJob]:
    """One pass over enabled processors.

    Returns at most one event per processor: the oldest event past the cursor
    whose ``event_type`` is in the processor's subscription. Unsubscribed
    events are invisible to the cursor — the worker only sees events it would
    actually handle. This keeps lag metrics meaningful and avoids wasted
    worker round-trips for events the processor would skip anyway.

    ``batch_size`` is currently a soft cap on the number of jobs returned per
    tick (≤ one per enabled processor), kept for future fan-out batches.
    """
    if batch_size < 1:
        raise BadRequestError("batch_size must be >= 1")

    processors = list(
        db.scalars(
            select(Processor)
            .where(Processor.enabled.is_(True))
            .order_by(Processor.name.asc())
        )
    )
    jobs: list[PendingDispatchJob] = []
    for processor in processors:
        if not processor.subscribed_event_types:
            continue
        row = db.execute(
            _matching_events_stmt(db, processor)
            .with_only_columns(FileEvent.id, FileEvent.offset, FileEvent.event_type)
            .order_by(FileEvent.offset.asc())
            .limit(1)
        ).one_or_none()
        if row is None:
            continue
        event_id, event_offset, event_type = row
        if processor.last_failed_event_id == event_id:
            log.info(
                "processor_dispatch_suppressed_failed_event",
                processor_id=str(processor.id),
                processor_name=processor.name,
                event_id=str(event_id),
                offset=int(event_offset),
            )
            continue
        jobs.append(
            PendingDispatchJob(
                processor_id=processor.id,
                event_id=event_id,
                event_offset=int(event_offset),
                event_type=event_type,
            )
        )
        if len(jobs) >= batch_size:
            break
    return jobs


# ---------------------------------------------------------------------------
# Worker execution: idempotent, transactional cursor advance.
# ---------------------------------------------------------------------------


def execute_processor_event(
    sm: sessionmaker[Session],
    *,
    processor_id: uuid.UUID,
    event_id: uuid.UUID,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
) -> ExecutionResult:
    """Run the substrate handler, emit the outcome event, and advance the cursor.

    One transaction holds a row lock on the processor for the whole handler run.
    This enforces per-processor concurrency=1 and commits DB side effects,
    outcome event, and cursor advance together on success. Cursor stays put on
    failure (head-of-line blocking, by design — admin can rewind or skip via
    the API).
    """
    started_at = time.perf_counter()
    with sm() as db:
        processor = db.scalar(
            select(Processor).where(Processor.id == processor_id).with_for_update()
        )
        if processor is None:
            log.warning(
                "processor_missing",
                processor_id=str(processor_id),
                event_id=str(event_id),
            )
            return _result("skipped_missing_processor", None, started_at)
        if not processor.enabled:
            log.info(
                "processor_skipped_disabled",
                processor_id=str(processor_id),
                event_id=str(event_id),
            )
            return _result("skipped_disabled", None, started_at)

        event = db.get(FileEvent, event_id)
        if event is None:
            log.warning(
                "processor_event_missing",
                processor_id=str(processor_id),
                event_id=str(event_id),
            )
            return _result("skipped_missing_event", None, started_at)

        if event.offset <= processor.last_committed_offset:
            return _result("skipped_already_processed", None, started_at)

        # Subscription is enforced by the dispatcher (collect_pending_jobs).
        # If a non-subscribed event still reaches here (admin retried a
        # stale enqueue, subscription was edited between dispatch and run,
        # etc.) we refuse to silently jump the cursor — that would skip work
        # the new subscription wants. Treat it as a missing event so the
        # cursor stays put and the next tick refreshes from the DB.
        if event.event_type not in processor.subscribed_event_types:
            log.warning(
                "processor_event_not_subscribed",
                processor_id=str(processor_id),
                event_id=str(event_id),
                event_type=event.event_type,
            )
            return _result("skipped_missing_event", None, started_at)

        if not _event_matches_folder_scopes(db, processor, event):
            log.warning(
                "processor_event_folder_scope_mismatch",
                processor_id=str(processor_id),
                event_id=str(event_id),
                folder_id=str(event.folder_id) if event.folder_id else None,
            )
            return _result("skipped_missing_event", None, started_at)

        substrate = get_substrate(processor.kind)
        ctx = ProcessorContext(
            processor_id=processor.id,
            processor_name=processor.name,
            config=dict(processor.config or {}),
            file_event=event,
        )
        error_class: str | None = None
        error_message: str | None = None
        try:
            substrate.handler(db, ctx)
        except Exception as exc:  # noqa: BLE001 - capture for outcome event
            error_class = type(exc).__name__
            error_message = str(exc)[:1000]
            log.warning(
                "processor_handler_failed",
                processor_id=str(processor_id),
                processor_name=processor.name,
                kind=processor.kind,
                event_id=str(event_id),
                event_offset=event.offset,
                error_class=error_class,
                error_message=error_message,
            )

        duration_ms = max(1, round((time.perf_counter() - started_at) * 1000))
        payload_base = {
            "processor": processor.name,
            "kind": processor.kind,
            "duration_ms": duration_ms,
            "source_event_id": str(event.id),
            "source_event_offset": event.offset,
            "source_event_type": event.event_type,
        }
        if error_class is None:
            create_file_event(
                db,
                event_type=f"processor.{processor.kind}.completed",
                status="succeeded",
                actor_user_id=event.actor_user_id,
                request_id=event.request_id,
                file_id=event.file_id,
                folder_id=event.folder_id,
                payload=payload_base,
            )
            processor.last_committed_offset = event.offset
            processor.last_committed_at = now()
            _clear_failure_state(processor)
            db.commit()
            return _result("ok", event.offset, started_at)

        processor.last_failed_event_id = event.id
        processor.last_failed_at = now()
        processor.last_error_class = error_class
        processor.last_error_message = error_message
        create_file_event(
            db,
            event_type=f"processor.{processor.kind}.failed",
            status="failed",
            actor_user_id=event.actor_user_id,
            request_id=event.request_id,
            file_id=event.file_id,
            folder_id=event.folder_id,
            payload={
                **payload_base,
                "error_class": error_class,
                "error_message": error_message,
            },
        )
        db.commit()
        return _result("failed", None, started_at)


def _result(status: str, advanced_to: int | None, started_at: float) -> ExecutionResult:
    return ExecutionResult(
        status=status,
        advanced_to_offset=advanced_to,
        duration_ms=max(1, round((time.perf_counter() - started_at) * 1000)),
    )


# ---------------------------------------------------------------------------
# Operator actions
# ---------------------------------------------------------------------------


def rewind_cursor(
    db: Session,
    *,
    processor_id: uuid.UUID,
    target_offset: int,
    reason: str,
    event_context: EventContext | None = None,
) -> Processor:
    """Move the cursor backward to *target_offset*.

    Set to 0 to replay everything. Passing the current offset is also useful
    after fixing a processor bug: it clears a stored failure and lets the
    dispatcher retry the same next event. Handlers must be idempotent — that is
    the whole point of the cursor model.
    """
    if target_offset < 0:
        raise BadRequestError("target_offset must be >= 0")
    if target_offset > PROCESSOR_MAX_REWIND_OFFSET:
        raise BadRequestError("target_offset is too large")

    cleaned_reason = _clean_reason(reason)
    processor = require_processor(db, processor_id)
    previous = processor.last_committed_offset
    if target_offset > previous:
        raise BadRequestError("target_offset cannot be ahead of the current cursor")
    processor.last_committed_offset = target_offset
    processor.last_committed_at = dt.datetime.now(dt.UTC)
    _clear_failure_state(processor)
    db.flush()

    if event_context is not None:
        audit_event_service.create_audit_event(
            db,
            operation="processor.cursor.rewound",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            metadata={
                "processor_id": str(processor.id),
                "name": processor.name,
                "from_offset": previous,
                "to_offset": target_offset,
                "reason": cleaned_reason,
            },
        )
    db.commit()
    db.refresh(processor)
    return processor


def skip_stuck_event(
    db: Session,
    *,
    processor_id: uuid.UUID,
    event_id: uuid.UUID,
    reason: str,
    event_context: EventContext | None = None,
) -> Processor:
    """Advance the cursor past *event_id* without running its handler.

    Used when a poisoned event blocks a processor and there's no path to a
    successful run. The action itself is auditable.
    """
    cleaned_reason = _clean_reason(reason)
    processor = require_processor(db, processor_id)
    event = db.get(FileEvent, event_id)
    if event is None:
        raise ResourceNotFound("File event not found")
    if event.offset <= processor.last_committed_offset:
        raise BadRequestError(
            "Event is already past the processor's cursor; nothing to skip"
        )
    next_event = db.execute(
        _matching_events_stmt(db, processor)
        .with_only_columns(FileEvent.id, FileEvent.offset)
        .order_by(FileEvent.offset.asc())
        .limit(1)
    ).one_or_none()
    if next_event is None or next_event.id != event.id:
        raise BadRequestError("Only the next event after the cursor can be skipped")

    previous = processor.last_committed_offset
    processor.last_committed_offset = event.offset
    processor.last_committed_at = dt.datetime.now(dt.UTC)
    _clear_failure_state(processor)
    db.flush()

    if event_context is not None:
        audit_event_service.create_audit_event(
            db,
            operation="processor.cursor.skipped",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            metadata={
                "processor_id": str(processor.id),
                "name": processor.name,
                "from_offset": previous,
                "to_offset": event.offset,
                "skipped_event_id": str(event.id),
                "skipped_event_type": event.event_type,
                "reason": cleaned_reason,
            },
        )
    db.commit()
    db.refresh(processor)
    return processor


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def clear_processors(db: Session) -> int:
    result = db.execute(delete(Processor))
    db.commit()
    return result.rowcount or 0


def list_substrates() -> list[str]:
    return list_substrate_kinds()


# ---------------------------------------------------------------------------
# Event matching
# ---------------------------------------------------------------------------


def _matching_events_stmt(db: Session, processor: Processor):
    stmt = select(FileEvent).where(
        FileEvent.offset > processor.last_committed_offset,
        FileEvent.event_type.in_(processor.subscribed_event_types),
    )
    folder_ids = _matching_folder_ids(db, processor)
    if folder_ids is not None:
        stmt = stmt.where(FileEvent.folder_id.in_(folder_ids))
    return stmt


def _event_matches_folder_scopes(
    db: Session, processor: Processor, event: FileEvent
) -> bool:
    folder_ids = _matching_folder_ids(db, processor)
    if folder_ids is None:
        return True
    return event.folder_id in folder_ids


def _matching_folder_ids(db: Session, processor: Processor) -> set[uuid.UUID] | None:
    scopes = processor.folder_scopes or []
    if not scopes:
        return None

    folder_ids: set[uuid.UUID] = set()
    for scope in scopes:
        folder_id = uuid.UUID(str(scope["folder_id"]))
        if scope.get("cascade", False):
            folder_ids.update(collect_descendant_folder_ids(db, folder_id))
        else:
            folder_ids.add(folder_id)
    return folder_ids


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


def _clean_required(value: str, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise BadRequestError(f"{field} cannot be empty")
    return cleaned


def _validate_folder_scopes(
    db: Session, folder_scopes: list[dict] | None
) -> list[dict[str, str | bool]]:
    if folder_scopes is None:
        return []
    if not isinstance(folder_scopes, list):
        raise BadRequestError("folder_scopes must be a list")

    scoped: dict[uuid.UUID, bool] = {}
    for raw_scope in folder_scopes:
        if not isinstance(raw_scope, dict):
            raise BadRequestError("folder_scopes entries must be objects")
        raw_folder_id = raw_scope.get("folder_id")
        if raw_folder_id is None:
            raise BadRequestError("folder_scopes entries require folder_id")
        try:
            folder_id = uuid.UUID(str(raw_folder_id))
        except ValueError as exc:
            raise BadRequestError("folder_scopes folder_id must be a UUID") from exc
        if db.get(Folder, folder_id) is None:
            raise ResourceNotFound("Folder not found")

        cascade = raw_scope.get("cascade", False)
        if not isinstance(cascade, bool):
            raise BadRequestError("folder_scopes cascade must be a boolean")
        scoped[folder_id] = scoped.get(folder_id, False) or cascade

    return [
        {"folder_id": str(folder_id), "cascade": cascade}
        for folder_id, cascade in scoped.items()
    ]


def _clean_reason(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise BadRequestError("reason is required")
    return cleaned


def _clear_failure_state(processor: Processor) -> None:
    processor.last_failed_event_id = None
    processor.last_failed_at = None
    processor.last_error_class = None
    processor.last_error_message = None


__all__ = [
    "ExecutionResult",
    "PendingDispatchJob",
    "ProcessorPage",
    "ProcessorWithLag",
    "clear_processors",
    "collect_pending_jobs",
    "create_processor",
    "delete_processor",
    "execute_processor_event",
    "get_processor_with_lag",
    "list_processors",
    "list_substrates",
    "require_processor",
    "rewind_cursor",
    "skip_stuck_event",
    "update_processor",
    "upsert_seed_processor",
]
