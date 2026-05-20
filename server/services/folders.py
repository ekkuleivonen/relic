import uuid
from collections import defaultdict
from dataclasses import dataclass

from enums import Permission, UserRole
from domain.exceptions import BadRequestError, ConflictError, PermissionDenied
from models import Blob, File, Folder, User
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from utils.logging import get_logger

from services import folder_access as folder_access_service
from services.s3_hotpath_cache import clear_list_objects_response_cache

log = get_logger(__name__)


@dataclass(frozen=True)
class FolderResult:
    """A folder enriched with its resolved path and effective permissions for a user."""

    folder: Folder
    path: str
    effective_permissions: int


def create_folder(
    db: Session,
    user: User,
    *,
    parent_id: uuid.UUID,
    name: str,
) -> FolderResult:
    name = _validate_name(name)
    parent = folder_access_service.require_folder(db, parent_id)
    folder_access_service.require_folder_permission_strict(
        db, user, parent.id, Permission.WRITE
    )

    folder = Folder(
        parent_id=parent.id,
        name=name,
    )
    db.add(folder)
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A folder with that name already exists here.") from exc

    db.refresh(folder)
    folder_access_service.clear_hotpath_cache(db)
    clear_list_objects_response_cache()
    log.info(
        "folder_create",
        folder_id=str(folder.id),
        parent_id=str(parent.id),
        name=name,
        user_id=str(user.id),
    )
    return _build_result(db, user, folder)


def update_folder(
    db: Session,
    user: User,
    *,
    folder_id: uuid.UUID,
    name: str | None = None,
    parent_id: uuid.UUID | None = None,
    preferred_bucket_id: uuid.UUID | None = None,
    set_preferred_bucket_id: bool = False,
) -> FolderResult:
    """Rename, move, and/or change storage preference (preference is admin-only)."""
    folder = folder_access_service.require_folder(db, folder_id)
    if folder.parent_id is None:
        if name is not None or parent_id is not None:
            raise BadRequestError("Cannot modify the root folder")

    folder_access_service.require_folder_permission_strict(
        db, user, folder.id, Permission.WRITE
    )

    if set_preferred_bucket_id and user.role != UserRole.ADMIN:
        raise PermissionDenied(
            "Only administrators can change folder storage preferences."
        )

    old_name = folder.name
    old_parent_id = folder.parent_id
    old_preferred_bucket_id = folder.preferred_bucket_id
    changed = False

    if name is not None:
        name = _validate_name(name)
        folder.name = name
        changed = True

    if parent_id is not None:
        if parent_id == folder.id:
            raise BadRequestError("Cannot move a folder into itself")
        descendants = set(_collect_descendant_ids(db, folder.id))
        if parent_id in descendants:
            raise BadRequestError(
                "Cannot move a folder into one of its own descendants (cycle)"
            )
        new_parent = folder_access_service.require_folder(db, parent_id)
        folder_access_service.require_folder_permission_strict(
            db, user, new_parent.id, Permission.WRITE
        )
        folder.parent_id = new_parent.id
        changed = True

    if set_preferred_bucket_id:
        if preferred_bucket_id is not None:
            from models import Bucket

            if db.get(Bucket, preferred_bucket_id) is None:
                raise BadRequestError("Preferred bucket does not exist")
        folder.preferred_bucket_id = preferred_bucket_id
        changed = True

    if not changed:
        return _build_result(db, user, folder)

    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A folder with that name already exists here.") from exc

    db.refresh(folder)
    folder_access_service.clear_hotpath_cache(db)
    clear_list_objects_response_cache()
    log.info(
        "folder_update",
        folder_id=str(folder.id),
        name=name if name is not None else None,
        parent_id=str(parent_id) if parent_id is not None else None,
        preferred_bucket_id=(
            str(preferred_bucket_id) if set_preferred_bucket_id else None
        ),
        user_id=str(user.id),
    )
    return _build_result(db, user, folder)


def delete_folder(
    db: Session,
    user: User,
    *,
    folder_id: uuid.UUID,
    recursive: bool = False,
) -> None:
    """
    Delete a folder subtree. Removes File rows and decrements Blob refcounts.

    Blobs whose refcount reaches 0 remain until ``storage_maintenance`` purge
    removes them via the arq worker (including object-store keys and counters).
    """
    folder = folder_access_service.require_folder(db, folder_id)
    if folder.parent_id is None:
        raise BadRequestError("Cannot delete the root folder")

    folder_access_service.require_folder_permission_strict(
        db, user, folder.id, Permission.DELETE
    )

    descendant_ids = _collect_descendant_ids(db, folder.id)
    all_ids = [folder.id, *descendant_ids]

    file_rows = list(db.scalars(select(File).where(File.folder_id.in_(all_ids))).all())
    has_children = bool(descendant_ids) or bool(file_rows)
    if has_children and not recursive:
        raise ConflictError(
            "Folder is not empty. Pass ?recursive=true to delete it and its contents."
        )

    blob_decrements: dict[uuid.UUID, int] = defaultdict(int)
    for file in file_rows:
        blob_decrements[file.blob_id] += 1

    if file_rows:
        db.execute(delete(File).where(File.folder_id.in_(all_ids)))

    if descendant_ids:
        db.execute(delete(Folder).where(Folder.id.in_(descendant_ids)))
    db.delete(folder)

    for blob_id, dec in blob_decrements.items():
        blob = db.get(Blob, blob_id)
        if blob is None:
            continue
        blob.refcount -= dec
        if blob.refcount < 0:
            blob.refcount = 0

    db.commit()
    folder_access_service.clear_hotpath_cache(db)
    clear_list_objects_response_cache()
    log.info(
        "folder_delete",
        folder_id=str(folder.id),
        recursive=recursive,
        descendant_count=len(descendant_ids),
        file_count=len(file_rows),
        user_id=str(user.id),
    )


def duplicate_folder(
    db: Session,
    user: User,
    *,
    folder_id: uuid.UUID,
    destination_parent_id: uuid.UUID,
    name: str,
    recursive: bool = True,
) -> FolderResult:
    name = _validate_name(name)
    source = folder_access_service.require_folder(db, folder_id)
    if source.parent_id is None:
        raise BadRequestError("Cannot duplicate the root folder")
    folder_access_service.require_folder_permission_strict(
        db, user, source.id, Permission.READ
    )

    destination = folder_access_service.require_folder(db, destination_parent_id)
    folder_access_service.require_folder_permission_strict(
        db, user, destination.id, Permission.WRITE
    )

    descendants_of_source = set(_collect_descendant_ids(db, source.id))
    if destination.id in descendants_of_source or destination.id == source.id:
        raise BadRequestError(
            "Cannot duplicate a folder into itself or one of its descendants"
        )

    cloned_root = Folder(
        parent_id=destination.id,
        name=name,
        preferred_bucket_id=source.preferred_bucket_id,
    )
    db.add(cloned_root)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A folder with that name already exists here.") from exc

    blob_increments: dict[uuid.UUID, int] = defaultdict(int)
    copied_files: list[tuple[uuid.UUID, File, File]] = []
    cloned_folders: list[Folder] = [cloned_root]

    def clone_files(source_id: uuid.UUID, target_id: uuid.UUID) -> None:
        files = list(db.scalars(select(File).where(File.folder_id == source_id)).all())
        for file in files:
            new_file = File(
                folder_id=target_id,
                blob_id=file.blob_id,
                actor_id=file.actor_id,
                name=file.name,
                meta=dict(file.meta),
            )
            db.add(new_file)
            db.flush()
            copied_files.append((source_id, file, new_file))
            blob_increments[file.blob_id] += 1

    clone_files(source.id, cloned_root.id)

    if recursive:
        # Walk the source subtree once, cloning folders + files breadth-first.
        children_by_parent = _children_by_parent(db)
        # Map source folder id -> cloned folder id
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
                db.add(clone)
                db.flush()
                cloned_folders.append(clone)
                cloned_by_source[child.id] = clone
                clone_files(child.id, clone.id)
                queue.append(child.id)

    for blob_id, inc in blob_increments.items():
        blob = db.get(Blob, blob_id)
        if blob is not None:
            blob.refcount += inc

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A folder with that name already exists here.") from exc

    db.refresh(cloned_root)
    folder_access_service.clear_hotpath_cache(db)
    clear_list_objects_response_cache()
    log.info(
        "folder_duplicate",
        source_id=str(source.id),
        cloned_id=str(cloned_root.id),
        recursive=recursive,
        user_id=str(user.id),
    )
    return _build_result(db, user, cloned_root)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise BadRequestError("Folder name cannot be empty")
    if "/" in cleaned:
        raise BadRequestError("Folder name cannot contain '/'")
    return cleaned


def _collect_descendant_ids(db: Session, folder_id: uuid.UUID) -> list[uuid.UUID]:
    """Return all descendants of `folder_id`, NOT including `folder_id` itself."""
    rows = db.execute(select(Folder.id, Folder.parent_id)).all()
    children_by_parent: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    for child_id, parent_id in rows:
        children_by_parent[parent_id].append(child_id)

    descendants: list[uuid.UUID] = []
    queue = list(children_by_parent.get(folder_id, []))
    while queue:
        current = queue.pop(0)
        descendants.append(current)
        queue.extend(children_by_parent.get(current, []))
    return descendants


def _children_by_parent(db: Session) -> dict[uuid.UUID, list[Folder]]:
    folders = list(db.scalars(select(Folder).order_by(Folder.name)).all())
    by_parent: dict[uuid.UUID, list[Folder]] = defaultdict(list)
    for folder in folders:
        if folder.parent_id is not None:
            by_parent[folder.parent_id].append(folder)
    return by_parent


def _build_result(db: Session, user: User, folder: Folder) -> FolderResult:
    path = folder_access_service.resolve_folder_path(db, folder)
    perms = folder_access_service.get_effective_permissions(db, user, folder.id)
    return FolderResult(
        folder=folder,
        path=path,
        effective_permissions=perms,
    )
