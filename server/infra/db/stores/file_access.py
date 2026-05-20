"""File row lookup with folder permission checks."""

import uuid

from domain.exceptions import ResourceNotFound
from enums import Permission
from infra.db.stores import folder_access
from infra.db.models import File, User
from ports.context import Actor
from sqlalchemy.orm import Session


def get_file_for_user(
    db: Session,
    file_id: uuid.UUID,
    user: User,
    permission: Permission,
) -> File:
    file = db.get(File, file_id)
    if file is None:
        raise ResourceNotFound("File not found")
    folder_access.require_folder_permission_strict(
        db, user, file.folder_id, permission
    )
    return file


def get_file_for_actor(
    db: Session,
    actor: Actor,
    file_id: uuid.UUID,
    permission: Permission,
) -> File:
    user = db.get(User, actor.id)
    if user is None:
        raise ResourceNotFound("User not found")
    return get_file_for_user(db, file_id, user, permission)
