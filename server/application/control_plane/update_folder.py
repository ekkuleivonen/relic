import uuid

from application.context import Actor, EventContext
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
    preferred_storage_backend_id: uuid.UUID | None = None,
    set_preferred_storage_backend_id: bool = False,
    event_context: EventContext | None = None,
) -> FolderResult:
    folder = uow.permissions.require_folder(folder_id)
    if folder.parent_id is None:
        if name is not None or parent_id is not None:
            raise BadRequestError("Cannot modify the root folder")

    uow.permissions.require_folder_permission(actor, folder.id, Permission.WRITE)

    user = uow.permissions.get_user(actor)
    if set_preferred_storage_backend_id and user.role != UserRole.ADMIN:
        raise PermissionDenied(
            "Only administrators can change folder storage preferences."
        )

    previous_name = folder.name
    from_parent_id = folder.parent_id
    previous_preferred_storage_backend_id = folder.preferred_storage_backend_id
    renamed = False
    moved = False

    if name is not None:
        folder.name = validate_folder_name(name)
        renamed = folder.name != previous_name

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
        if folder.parent_id != new_parent.id:
            moved = True
        folder.parent_id = new_parent.id

    if set_preferred_storage_backend_id:
        if preferred_storage_backend_id is not None:
            try:
                uow.storage_backends.get(preferred_storage_backend_id)
            except ResourceNotFound as exc:
                raise BadRequestError("Preferred bucket does not exist") from exc
        folder.preferred_storage_backend_id = preferred_storage_backend_id
        if (
            event_context is not None
            and folder.preferred_storage_backend_id
            != previous_preferred_storage_backend_id
        ):
            uow.audit.record(
                operation="folder.preferred_storage_backend.updated",
                event_context=event_context,
                metadata={
                    "folder_id": str(folder.id),
                    "name": folder.name,
                    "previous_preferred_storage_backend_id": (
                        str(previous_preferred_storage_backend_id)
                        if previous_preferred_storage_backend_id is not None
                        else None
                    ),
                    "preferred_storage_backend_id": (
                        str(folder.preferred_storage_backend_id)
                        if folder.preferred_storage_backend_id is not None
                        else None
                    ),
                },
            )

    if not renamed and not moved and not set_preferred_storage_backend_id:
        return folder_result(uow, actor, folder)

    uow.folders.save(folder)
    request_id = event_context.request_id if event_context else None
    if renamed and not moved:
        from application.control_plane import filesystem_event_emission

        filesystem_event_emission.emit_folder_renamed(
            uow,
            folder=folder,
            previous_name=previous_name,
            actor_id=actor.id,
            request_id=request_id,
        )
    if moved:
        assert from_parent_id is not None
        from application.control_plane import filesystem_event_emission

        filesystem_event_emission.emit_folder_moved(
            uow,
            folder=folder,
            from_parent_id=from_parent_id,
            actor_id=actor.id,
            request_id=request_id,
        )
    uow.cache.invalidate_folder_hotpath(uow.session)
    uow.cache.invalidate_list_objects()
    log.info(
        "folder_update",
        folder_id=str(folder.id),
        name=name if name is not None else None,
        parent_id=str(parent_id) if parent_id is not None else None,
        preferred_storage_backend_id=(
            str(preferred_storage_backend_id) if set_preferred_storage_backend_id else None
        ),
        user_id=str(actor.id),
    )
    return folder_result(uow, actor, folder)
