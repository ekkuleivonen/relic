"""Audit event emission port (AuditSink)."""

import datetime as dt
import uuid
from typing import Any, Protocol

from application.context import EventContext


class AuditPort(Protocol):
    def record(
        self,
        *,
        operation: str,
        event_context: EventContext | None,
        metadata: dict[str, Any],
        db_latency_ms: int = 0,
    ) -> None: ...

    def emit(
        self,
        *,
        operation: str,
        status: str = "succeeded",
        actor_id: uuid.UUID | None = None,
        request_id: str | None = None,
        job: str | None = None,
        batch_id: uuid.UUID | None = None,
        bucket_id: uuid.UUID | None = None,
        blob_id: uuid.UUID | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    def clear_all(self) -> int: ...

    def trim_older_than(
        self, *, retention_days: int, now: dt.datetime | None = None
    ) -> int: ...
