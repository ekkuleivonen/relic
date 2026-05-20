import uuid

from ports.context import EventContext
from infra.db.stores import folder_access
from infra.db.stores.folder_access_types import FolderAccessRow
from application.uow import UnitOfWork


def grant_folder_access(
    uow: UnitOfWork,
    *,
    actor_id: uuid.UUID,
    folder_id: uuid.UUID,
    permissions: int,
    event_context: EventContext | None = None,
) -> FolderAccessRow:
    row = folder_access.grant_folder_access(
        uow.session,
        actor_id=actor_id,
        folder_id=folder_id,
        permissions=permissions,
        event_context=event_context,
    )
    uow.cache.invalidate_folder_hotpath(uow.session)
    uow.cache.invalidate_list_objects()
    return row


def revoke_folder_access(
    uow: UnitOfWork,
    *,
    access_id: uuid.UUID,
    event_context: EventContext | None = None,
) -> None:
    folder_access.revoke_folder_access(
        uow.session,
        access_id,
        event_context=event_context,
    )
    uow.cache.invalidate_folder_hotpath(uow.session)
    uow.cache.invalidate_list_objects()
