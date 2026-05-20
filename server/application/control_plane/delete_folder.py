import uuid
from collections import defaultdict

from application.context import Actor, EventContext
from application.control_plane import filesystem_event_emission
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError, ConflictError
from enums import Permission
from infra.db.models import Blob, Folder
from sqlalchemy import select
from utils.logging import get_logger

log = get_logger(__name__)


def _descendant_folder_count_in_set(
    uow: UnitOfWork, folder_id: uuid.UUID, folder_ids: set[uuid.UUID]
) -> int:
    return len(
        [
            descendant_id
            for descendant_id in uow.folders.collect_descendant_ids(folder_id)
            if descendant_id in folder_ids
        ]
    )


def _delete_event_visibility_folder_id(
    folder: Folder,
    delete_ids: set[uuid.UUID],
    folders_by_id: dict[uuid.UUID, Folder],
) -> uuid.UUID:
    parent_id = folder.parent_id
    while parent_id is not None and parent_id in delete_ids:
        parent_id = folders_by_id[parent_id].parent_id
    return parent_id if parent_id is not None else folder.id


def delete_folder(
    uow: UnitOfWork,
    *,
    actor: Actor,
    folder_id: uuid.UUID,
    recursive: bool = False,
    event_context: EventContext | None = None,
) -> None:
    folder = uow.permissions.require_folder(folder_id)
    if folder.parent_id is None:
        raise BadRequestError("Cannot delete the root folder")

    uow.permissions.require_folder_permission(actor, folder.id, Permission.DELETE)

    descendant_ids = uow.folders.collect_descendant_ids(folder.id)
    all_ids = [folder.id, *descendant_ids]
    folder_ids = set(all_ids)

    file_rows = uow.files.list_in_folders(all_ids)
    has_children = bool(descendant_ids) or bool(file_rows)
    if has_children and not recursive:
        raise ConflictError(
            "Folder is not empty. Pass ?recursive=true to delete it and its contents."
        )

    request_id = event_context.request_id if event_context else None
    blob_decrements: dict[uuid.UUID, int] = defaultdict(int)
    for file in file_rows:
        blob = uow.session.get(Blob, file.blob_id)
        if blob is not None:
            filesystem_event_emission.emit_file_deleted(
                uow,
                file=file,
                blob=blob,
                actor_id=actor.id,
                request_id=request_id,
            )
        blob_decrements[file.blob_id] += 1

    files_by_folder: dict[uuid.UUID, int] = defaultdict(int)
    for file in file_rows:
        files_by_folder[file.folder_id] += 1

    folders_by_id = {
        row.id: row
        for row in uow.session.scalars(
            select(Folder).where(Folder.id.in_(all_ids))
        ).all()
    }
    for deleted_folder_id in reversed(descendant_ids + [folder.id]):
        deleted_folder = folders_by_id[deleted_folder_id]
        filesystem_event_emission.emit_folder_deleted(
            uow,
            folder=deleted_folder,
            visibility_folder_id=_delete_event_visibility_folder_id(
                deleted_folder, folder_ids, folders_by_id
            ),
            recursive=recursive,
            descendant_folder_count=_descendant_folder_count_in_set(
                uow, deleted_folder_id, folder_ids
            ),
            file_count=files_by_folder[deleted_folder_id],
            actor_id=actor.id,
            request_id=request_id,
        )

    if event_context is not None:
        uow.audit.record(
            operation="folder.deleted",
            event_context=event_context,
            metadata={
                "folder_id": str(folder.id),
                "name": folder.name,
                "recursive": recursive,
                "descendant_folder_count": len(descendant_ids),
                "file_count": len(file_rows),
            },
        )

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
