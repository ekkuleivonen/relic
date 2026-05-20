import uuid

from application.context import Actor
from application.control_plane.folder_use_cases import folder_result, validate_folder_name
from application.control_plane.folders import FolderResult
from application.uow import UnitOfWork
from enums import Permission
from ports.entities import File, Folder
from utils.logging import get_logger

log = get_logger(__name__)


def create_folder(
    uow: UnitOfWork,
    *,
    actor: Actor,
    parent_id: uuid.UUID,
    name: str,
) -> FolderResult:
    name = validate_folder_name(name)
    parent = uow.permissions.require_folder(parent_id)
    uow.permissions.require_folder_permission(actor, parent.id, Permission.WRITE)

    folder = Folder(parent_id=parent.id, name=name)
    uow.folders.add(folder)
    uow.cache.invalidate_folder_hotpath(uow.session)
    uow.cache.invalidate_list_objects()
    log.info(
        "folder_create",
        folder_id=str(folder.id),
        parent_id=str(parent.id),
        name=name,
        user_id=str(actor.id),
    )
    return folder_result(uow, actor, folder)
