import uuid

from application.context import Actor
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError
from domain.files.meta import patch_meta
from enums import Permission
from infra.db.models import File


def patch_file_meta(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_id: uuid.UUID,
    patch: dict,
) -> File:
    """Deep-merge *patch* into the file's consumer-owned metadata."""
    file = uow.permissions.get_file_for_actor(
        actor, file_id, Permission.ENRICH
    )
    try:
        file.meta = patch_meta(file.meta, patch)
    except TypeError as exc:
        raise BadRequestError(str(exc)) from exc
    uow.files.save(file)
    uow.cache.invalidate_list_objects()
    return file
