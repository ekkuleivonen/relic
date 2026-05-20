import uuid
from collections import defaultdict

from application.context import Actor
from application.control_plane import file_event_emission
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError, ConflictError
from enums import Permission
from infra.db.models import Blob
from utils.logging import get_logger

log = get_logger(__name__)


def delete_folder(
    uow: UnitOfWork,
    *,
    actor: Actor,
    folder_id: uuid.UUID,
    recursive: bool = False,
) -> None:
    folder = uow.permissions.require_folder(folder_id)
    if folder.parent_id is None:
        raise BadRequestError("Cannot delete the root folder")

    uow.permissions.require_folder_permission(actor, folder.id, Permission.DELETE)

    descendant_ids = uow.folders.collect_descendant_ids(folder.id)
    all_ids = [folder.id, *descendant_ids]

    file_rows = uow.files.list_in_folders(all_ids)
    has_children = bool(descendant_ids) or bool(file_rows)
    if has_children and not recursive:
        raise ConflictError(
            "Folder is not empty. Pass ?recursive=true to delete it and its contents."
        )

    blob_decrements: dict[uuid.UUID, int] = defaultdict(int)
    for file in file_rows:
        blob = uow.session.get(Blob, file.blob_id)
        if blob is not None:
            file_event_emission.emit_file_deleted(
                uow,
                file=file,
                blob=blob,
                actor_id=actor.id,
            )
        blob_decrements[file.blob_id] += 1

    if file_rows:
        uow.files.delete_in_folders(all_ids)

    if descendant_ids:
        uow.folders.delete_folders_by_ids(descendant_ids)
    uow.folders.delete(folder)

    uow.files.adjust_blob_refcounts({blob_id: -dec for blob_id, dec in blob_decrements.items()})
    uow.cache.invalidate_folder_hotpath(uow.session)
    uow.cache.invalidate_list_objects()
    log.info(
        "folder_delete",
        folder_id=str(folder.id),
        recursive=recursive,
        descendant_count=len(descendant_ids),
        file_count=len(file_rows),
        user_id=str(actor.id),
    )
