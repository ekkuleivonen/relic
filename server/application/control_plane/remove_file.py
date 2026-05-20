"""Shared file removal — control plane and S3 gateway."""

import uuid

from application.context import Actor
from application.control_plane import file_event_emission
from application.uow import UnitOfWork
from enums import Permission
from infra.db.models import Blob
from ports.entities import File


def remove_file_record(
    uow: UnitOfWork,
    *,
    file: File,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    """Delete a file row and decrement blob refcount. Does not delete remote bytes."""
    blob = file.blob
    if blob is None and uow.session is not None:
        blob = uow.session.get(Blob, file.blob_id)
    if blob is not None:
        file_event_emission.emit_file_deleted(
            uow,
            file=file,
            blob=blob,
            actor_id=actor_id,
            request_id=request_id,
        )
    uow.files.delete(file)
    uow.cache.invalidate_list_objects()
    uow.cache.invalidate_folder_hotpath(uow.session)


def remove_file_by_id(
    uow: UnitOfWork, *, actor: Actor, file_id: uuid.UUID
) -> None:
    file = uow.permissions.get_file_for_actor(actor, file_id, Permission.DELETE)
    remove_file_record(uow, file=file, actor_id=actor.id)
