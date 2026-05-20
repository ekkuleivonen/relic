import uuid
from collections import defaultdict

from application.context import Actor
from application.control_plane.folder_use_cases import folder_result, validate_folder_name
from application.control_plane.folders import FolderResult
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError
from enums import Permission
from ports.entities import File, Folder
from utils.logging import get_logger

log = get_logger(__name__)


def duplicate_folder(
    uow: UnitOfWork,
    *,
    actor: Actor,
    folder_id: uuid.UUID,
    destination_parent_id: uuid.UUID,
    name: str,
    recursive: bool = True,
) -> FolderResult:
    name = validate_folder_name(name)
    source = uow.permissions.require_folder(folder_id)
    if source.parent_id is None:
        raise BadRequestError("Cannot duplicate the root folder")
    uow.permissions.require_folder_permission(actor, source.id, Permission.READ)

    destination = uow.permissions.require_folder(destination_parent_id)
    uow.permissions.require_folder_permission(actor, destination.id, Permission.WRITE)

    descendants_of_source = set(uow.folders.collect_descendant_ids(source.id))
    if destination.id in descendants_of_source or destination.id == source.id:
        raise BadRequestError(
            "Cannot duplicate a folder into itself or one of its descendants"
        )

    cloned_root = Folder(
        parent_id=destination.id,
        name=name,
        preferred_bucket_id=source.preferred_bucket_id,
    )
    uow.folders.add(cloned_root)

    blob_increments: dict[uuid.UUID, int] = defaultdict(int)

    def clone_files(source_id: uuid.UUID, target_id: uuid.UUID) -> None:
        for file in uow.files.list_in_folders([source_id]):
            new_file = File(
                folder_id=target_id,
                blob_id=file.blob_id,
                actor_id=file.actor_id,
                name=file.name,
                meta=dict(file.meta),
            )
            uow.files.add(new_file)
            blob_increments[file.blob_id] += 1

    clone_files(source.id, cloned_root.id)

    if recursive:
        children_by_parent = uow.folders.children_by_parent()
        cloned_by_source: dict[uuid.UUID, Folder] = {source.id: cloned_root}
        queue = [source.id]
        while queue:
            src_id = queue.pop(0)
            target = cloned_by_source[src_id]
            for child in children_by_parent.get(src_id, []):
                clone = Folder(
                    parent_id=target.id,
                    name=child.name,
                    preferred_bucket_id=child.preferred_bucket_id,
                )
                uow.folders.add(clone)
                cloned_by_source[child.id] = clone
                clone_files(child.id, clone.id)
                queue.append(child.id)

    uow.files.adjust_blob_refcounts(blob_increments)
    uow.cache.invalidate_folder_hotpath(uow.session)
    uow.cache.invalidate_list_objects()
    log.info(
        "folder_duplicate",
        source_id=str(source.id),
        cloned_id=str(cloned_root.id),
        recursive=recursive,
        user_id=str(actor.id),
    )
    return folder_result(uow, actor, cloned_root)
