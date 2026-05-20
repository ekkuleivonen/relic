import uuid

from application.context import Actor
from application.control_plane import file_event_emission
from application.uow import UnitOfWork
from domain.files.naming import normalize_requested_file_name, validate_filename
from enums import Permission
from infra.db.models import Blob
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

    from_folder_id = file.folder_id
    previous_name = file.name
    file.folder_id = destination.id
    file.name = new_name
    uow.files.save(file)
    uow.cache.invalidate_list_objects()
    blob = uow.session.get(Blob, file.blob_id)
    if blob is not None:
        if from_folder_id == destination.id:
            file_event_emission.emit_file_renamed(
                uow,
                file=file,
                blob=blob,
                previous_name=previous_name,
                actor_id=actor.id,
            )
        else:
            file_event_emission.emit_file_moved(
                uow,
                file=file,
                blob=blob,
                from_folder_id=from_folder_id,
                previous_name=previous_name,
                actor_id=actor.id,
            )
    return file
