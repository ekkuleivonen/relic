"""Shared file removal — control plane and S3 gateway."""

import uuid

from application.context import Actor
from application.uow import UnitOfWork
from enums import Permission
from infra.db.models import File


def remove_file_record(uow: UnitOfWork, *, file: File) -> None:
    """Delete a file row and decrement blob refcount. Does not delete remote bytes."""
    uow.files.delete(file)
    uow.cache.invalidate_list_objects()
    uow.cache.invalidate_folder_hotpath(uow.session)


def remove_file_by_id(
    uow: UnitOfWork, *, actor: Actor, file_id: uuid.UUID
) -> None:
    file = uow.permissions.get_file_for_actor(actor, file_id, Permission.DELETE)
    remove_file_record(uow, file=file)
