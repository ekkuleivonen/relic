import datetime as dt
import uuid
from typing import Any

from infra.db.stores import filesystem_events as filesystem_events_store
from infra.db.stores.filesystem_events import FilesystemEventPage
from ports.filesystem_events import FilesystemEventPort
from sqlalchemy.orm import Session


class SqlAlchemyFilesystemEventPort:
    def __init__(self, session: Session) -> None:
        self._session = session

    def emit(
        self,
        *,
        event_type: str,
        folder_id: uuid.UUID,
        file_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        request_id: str | None = None,
        payload: dict[str, Any],
    ) -> None:
        filesystem_events_store.create_filesystem_event(
            self._session,
            event_type=event_type,
            folder_id=folder_id,
            file_id=file_id,
            actor_id=actor_id,
            request_id=request_id,
            payload=payload,
        )

    def list_events(
        self,
        user,
        *,
        after: int,
        folder_id: uuid.UUID | None,
        recursive: bool,
        event_types: frozenset[str] | None,
        limit: int,
    ) -> FilesystemEventPage:
        return filesystem_events_store.list_filesystem_events(
            self._session,
            user,
            after=after,
            folder_id=folder_id,
            recursive=recursive,
            event_types=event_types,
            limit=limit,
        )

    def trim_older_than(
        self, *, retention_days: int, now: dt.datetime | None = None
    ) -> int:
        return filesystem_events_store.trim_filesystem_events_older_than(
            self._session,
            retention_days=retention_days,
            now=now,
        )


def build_filesystem_event_port(session: Session) -> FilesystemEventPort:
    return SqlAlchemyFilesystemEventPort(session)
