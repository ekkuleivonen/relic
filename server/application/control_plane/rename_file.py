import uuid

from application.context import Actor
from application.control_plane import file_event_emission
from application.uow import UnitOfWork
from domain.files.naming import normalize_requested_file_name
from enums import Permission
from infra.db.models import Blob
from ports.entities import File


def rename_file(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_id: uuid.UUID,
    name: str,
) -> File:
    """Rename a file in place."""
    file = uow.permissions.get_file_for_actor(
        actor, file_id, Permission.WRITE
    )
    new_name = normalize_requested_file_name(
        current_name=file.name, requested_name=name
    )

    if file.name == new_name:
        return file

    uow.files.ensure_name_available(file.folder_id, new_name)

    previous_name = file.name
    file.name = new_name
    uow.files.save(file)
    uow.cache.invalidate_list_objects()
    blob = uow.session.get(Blob, file.blob_id)
    if blob is not None:
        file_event_emission.emit_file_renamed(
            uow,
            file=file,
            blob=blob,
            previous_name=previous_name,
            actor_id=actor.id,
        )
    return file
