"""File event read queries."""

import uuid

from application.uow import UnitOfWork
from domain.exceptions import BadRequestError
from domain.file_events.types import FILE_EVENT_TYPES
from enums import UserRole
from infra.db.stores.file_events import FileEventPage
from ports.entities import User


def list_file_events(
    uow: UnitOfWork,
    *,
    user: User,
    after: int,
    folder_id: uuid.UUID | None,
    recursive: bool,
    event_types: list[str] | None,
    limit: int,
) -> FileEventPage:
    parsed_types: frozenset[str] | None = None
    if event_types is not None:
        parsed_types = frozenset(event_types)
        if not parsed_types.issubset(FILE_EVENT_TYPES):
            unknown = parsed_types - FILE_EVENT_TYPES
            raise BadRequestError(
                f"Unsupported file event types: {sorted(unknown)}"
            )

    return uow.file_events.list_events(
        user,
        after=after,
        folder_id=folder_id,
        recursive=recursive,
        event_types=parsed_types,
        limit=limit,
    )


def user_can_poll_all_events(user: User) -> bool:
    return user.role == UserRole.ADMIN
