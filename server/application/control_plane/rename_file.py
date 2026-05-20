import uuid

from application.context import Actor
from application.uow import UnitOfWork
from domain.files.naming import normalize_requested_file_name
from enums import Permission
from infra.db.models import File


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

    file.name = new_name
    uow.files.save(file)
    uow.cache.invalidate_list_objects()
    return file
