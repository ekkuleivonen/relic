"""Filesystem event emission port (integrator subscription log)."""

import datetime as dt
import uuid
from typing import Any, Protocol

from infra.db.stores.filesystem_events import FilesystemEventPage


class FilesystemEventPort(Protocol):
    def emit(
        self,
        *,
        event_type: str,
        folder_id: uuid.UUID,
        file_id: uuid.UUID | None = None,
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
    ) -> FilesystemEventPage: ...

    def trim_older_than(
        self, *, retention_days: int, now: dt.datetime | None = None
    ) -> int: ...
