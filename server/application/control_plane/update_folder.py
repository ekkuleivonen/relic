import uuid

from application.context import Actor
from application.control_plane.folder_use_cases import folder_result, validate_folder_name
from application.control_plane.folders import FolderResult
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError, PermissionDenied, ResourceNotFound
from enums import Permission, UserRole
from utils.logging import get_logger

log = get_logger(__name__)


def update_folder(
    uow: UnitOfWork,
    *,
    actor: Actor,
    folder_id: uuid.UUID,
    name: str | None = None,
    parent_id: uuid.UUID | None = None,
    preferred_bucket_id: uuid.UUID | None = None,
    set_preferred_bucket_id: bool = False,
) -> FolderResult:
    folder = uow.permissions.require_folder(folder_id)
    if folder.parent_id is None:
        if name is not None or parent_id is not None:
            raise BadRequestError("Cannot modify the root folder")

    uow.permissions.require_folder_permission(actor, folder.id, Permission.WRITE)

    user = uow.permissions.get_user(actor)
    if set_preferred_bucket_id and user.role != UserRole.ADMIN:
        raise PermissionDenied(
            "Only administrators can change folder storage preferences."
        )

    changed = False

    if name is not None:
        folder.name = validate_folder_name(name)
        changed = True

    if parent_id is not None:
        if parent_id == folder.id:
            raise BadRequestError("Cannot move a folder into itself")
        descendants = set(uow.folders.collect_descendant_ids(folder.id))
        if parent_id in descendants:
            raise BadRequestError(
                "Cannot move a folder into one of its own descendants (cycle)"
            )
        new_parent = uow.permissions.require_folder(parent_id)
        uow.permissions.require_folder_permission(
            actor, new_parent.id, Permission.WRITE
        )
        folder.parent_id = new_parent.id
        changed = True

    if set_preferred_bucket_id:
        if preferred_bucket_id is not None:
            try:
                uow.buckets.get(preferred_bucket_id)
            except ResourceNotFound as exc:
                raise BadRequestError("Preferred bucket does not exist") from exc
        folder.preferred_bucket_id = preferred_bucket_id
        changed = True

    if not changed:
        return folder_result(uow, actor, folder)

    uow.folders.save(folder)
    uow.cache.invalidate_folder_hotpath(uow.session)
    uow.cache.invalidate_list_objects()
    log.info(
        "folder_update",
        folder_id=str(folder.id),
        name=name if name is not None else None,
        parent_id=str(parent_id) if parent_id is not None else None,
        preferred_bucket_id=(
            str(preferred_bucket_id) if set_preferred_bucket_id else None
        ),
        user_id=str(actor.id),
    )
    return folder_result(uow, actor, folder)
