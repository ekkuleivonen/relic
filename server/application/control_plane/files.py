import uuid

from application.context import Actor
from application.uow import UnitOfWork
from enums import Permission
from ports.entities import File


def get_file(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_id: uuid.UUID,
) -> File:
    file = uow.permissions.get_file_for_actor(
        actor, file_id, Permission.READ
    )
    return uow.files.ensure_blob_loaded(file)
