import uuid

from application.context import Actor
from application.uow import UnitOfWork
from domain.files.naming import normalize_requested_file_name, validate_filename
from enums import Permission
from ports.entities import File


def move_file(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_id: uuid.UUID,
    destination_folder_id: uuid.UUID,
    name: str | None,
) -> File:
    """Move a file to another folder. Atomic; blob refcount unchanged."""
    file = uow.permissions.get_file_for_actor(
        actor, file_id, Permission.DELETE
    )
    destination = uow.permissions.require_folder(destination_folder_id)
    uow.permissions.require_folder_permission(
        actor, destination.id, Permission.WRITE
    )

    if name is not None:
        new_name = normalize_requested_file_name(
            current_name=file.name, requested_name=name
        )
    else:
        new_name = file.name
        validate_filename(new_name)

    if file.folder_id == destination.id and file.name == new_name:
        return file

    uow.files.ensure_name_available(destination.id, new_name)

    file.folder_id = destination.id
    file.name = new_name
    uow.files.save(file)
    uow.cache.invalidate_list_objects()
    return file
