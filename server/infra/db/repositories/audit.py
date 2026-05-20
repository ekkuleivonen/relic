import datetime as dt
import uuid
from typing import Any

from ports.context import EventContext
from infra.db.stores.audit_events import create_audit_event
from infra.db.models import AuditEvent
from ports.audit import AuditPort
from sqlalchemy import delete
from sqlalchemy.orm import Session


class SqlAlchemyAuditPort:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        operation: str,
        event_context: EventContext | None,
        metadata: dict[str, Any],
        db_latency_ms: int = 0,
    ) -> None:
        del db_latency_ms
        if event_context is None:
            return
        self.emit(
            operation=operation,
            actor_id=event_context.actor_id,
            request_id=event_context.request_id,
            metadata=metadata,
        )

    def emit(
        self,
        *,
        operation: str,
        status: str = "succeeded",
        actor_id: uuid.UUID | None = None,
        request_id: str | None = None,
        job: str | None = None,
        batch_id: uuid.UUID | None = None,
        storage_backend_id: uuid.UUID | None = None,
        blob_id: uuid.UUID | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        create_audit_event(
            self._session,
            operation=operation,
            status=status,
            actor_id=actor_id,
            request_id=request_id,
            job=job,
            batch_id=batch_id,
            storage_backend_id=storage_backend_id,
            blob_id=blob_id,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def clear_all(self) -> int:
        result = self._session.execute(delete(AuditEvent))
        return result.rowcount or 0

    def trim_older_than(
        self, *, retention_days: int, now: dt.datetime | None = None
    ) -> int:
        effective_now = now or dt.datetime.now(dt.UTC)
        cutoff = effective_now - dt.timedelta(days=retention_days)
        result = self._session.execute(
            delete(AuditEvent).where(AuditEvent.created_at < cutoff)
        )
        return result.rowcount or 0


def build_audit_port(session: Session) -> AuditPort:
    return SqlAlchemyAuditPort(session)
