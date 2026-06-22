"""Filesystem event read queries."""

import uuid

from application.uow import UnitOfWork
from domain.exceptions import BadRequestError
from domain.filesystem_events.types import FILESYSTEM_EVENT_TYPES
from enums import UserRole
from infra.db.stores.filesystem_events import FilesystemEventPage
from ports.entities import User


def list_filesystem_events(
    uow: UnitOfWork,
    *,
    user: User,
    after: int,
    folder_id: uuid.UUID | None,
    recursive: bool,
    event_types: list[str] | None,
    limit: int,
) -> FilesystemEventPage:
    parsed_types: frozenset[str] | None = None
    if event_types is not None:
        parsed_types = frozenset(event_types)
        if not parsed_types.issubset(FILESYSTEM_EVENT_TYPES):
            unknown = parsed_types - FILESYSTEM_EVENT_TYPES
            raise BadRequestError(
                f"Unsupported filesystem event types: {sorted(unknown)}"
            )

    return uow.filesystem_events.list_events(
        user,
        after=after,
        folder_id=folder_id,
        recursive=recursive,
        event_types=parsed_types,
        limit=limit,
    )


def user_can_poll_all_events(user: User) -> bool:
    return user.role == UserRole.ADMIN
