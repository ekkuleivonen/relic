"""File event emission port (integrator subscription log)."""

import datetime as dt
import uuid
from typing import Any, Protocol

from infra.db.stores.file_events import FileEventPage


class FileEventPort(Protocol):
    def emit(
        self,
        *,
        event_type: str,
        file_id: uuid.UUID,
        folder_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        request_id: str | None = None,
        payload: dict[str, Any],
    ) -> None: ...

    def list_events(
        self,
        user,
        *,
        after: int,
        folder_id: uuid.UUID | None,
        recursive: bool,
        event_types: frozenset[str] | None,
        limit: int,
    ) -> FileEventPage: ...

    def trim_older_than(
        self, *, retention_days: int, now: dt.datetime | None = None
    ) -> int: ...
