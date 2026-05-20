import datetime as dt
import uuid
from typing import Any

from infra.db.stores import file_events as file_events_store
from infra.db.stores.file_events import FileEventPage
from ports.file_events import FileEventPort
from sqlalchemy.orm import Session


class SqlAlchemyFileEventPort:
    def __init__(self, session: Session) -> None:
        self._session = session

    def emit(
        self,
        *,
        event_type: str,
        file_id: uuid.UUID,
        folder_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        request_id: str | None = None,
        payload: dict[str, Any],
    ) -> None:
        file_events_store.create_file_event(
            self._session,
            event_type=event_type,
            file_id=file_id,
            folder_id=folder_id,
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
    ) -> FileEventPage:
        return file_events_store.list_file_events(
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
        return file_events_store.trim_file_events_older_than(
            self._session,
            retention_days=retention_days,
            now=now,
        )


def build_file_event_port(session: Session) -> FileEventPort:
    return SqlAlchemyFileEventPort(session)
