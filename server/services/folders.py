import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from managers.exceptions import BadRequestError, ConflictError, PermissionDenied, ResourceNotFound
from models import Blob, File, Folder, User
from schema_plan import Permission, UserRole
from services import folder_access as folder_access_service
from utils.logging import get_logger

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
        cooldown_days=None,
        min_tier=None,
    )
    db.add(folder)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A folder with that name already exists here.") from exc

    db.refresh(folder)
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
    min_tier: int | None = None,
    cooldown_days: int | None = None,
    set_min_tier: bool = False,
    set_cooldown_days: bool = False,
) -> FolderResult:
    """Rename, move, and/or change storage policy (policy fields are admin-only)."""
    folder = folder_access_service.require_folder(db, folder_id)
    if folder.parent_id is None:
        if name is not None or parent_id is not None:
            raise BadRequestError("Cannot modify the root folder")

    folder_access_service.require_folder_permission_strict(
        db, user, folder.id, Permission.WRITE
    )

    if set_min_tier or set_cooldown_days:
        if user.role != UserRole.ADMIN:
            raise PermissionDenied(
                "Only administrators can change folder storage policy."
            )

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

    if set_min_tier:
        if folder.parent_id is None and min_tier is None:
            raise BadRequestError(
                "The root folder must set an explicit minimum storage tier."
            )
        folder.min_tier = min_tier
        changed = True

    if set_cooldown_days:
        folder.cooldown_days = cooldown_days
        changed = True

    if not changed:
        return _build_result(db, user, folder)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A folder with that name already exists here.") from exc

    db.refresh(folder)
    log.info(
        "folder_update",
        folder_id=str(folder.id),
        name=name if name is not None else None,
        parent_id=str(parent_id) if parent_id is not None else None,
        min_tier=min_tier if set_min_tier else None,
        cooldown_days=cooldown_days if set_cooldown_days else None,
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
    folder = folder_access_service.require_folder(db, folder_id)
    if folder.parent_id is None:
        raise BadRequestError("Cannot delete the root folder")

    folder_access_service.require_folder_permission_strict(
        db, user, folder.id, Permission.DELETE
    )

    descendant_ids = _collect_descendant_ids(db, folder.id)
    all_ids = [folder.id, *descendant_ids]

    file_rows = list(
        db.scalars(select(File).where(File.folder_id.in_(all_ids))).all()
    )
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
        if blob.refcount <= 0:
            db.delete(blob)

    db.commit()
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
        cooldown_days=source.cooldown_days,
        min_tier=source.min_tier,
    )
    db.add(cloned_root)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A folder with that name already exists here.") from exc

    blob_increments: dict[uuid.UUID, int] = defaultdict(int)

    def clone_files(source_id: uuid.UUID, target_id: uuid.UUID) -> None:
        files = list(
            db.scalars(select(File).where(File.folder_id == source_id)).all()
        )
        for file in files:
            db.add(
                File(
                    folder_id=target_id,
                    blob_id=file.blob_id,
                    uploaded_by=file.uploaded_by,
                    name=file.name,
                    parse_status=file.parse_status,
                    meta=dict(file.meta),
                )
            )
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
                    cooldown_days=child.cooldown_days,
                    min_tier=child.min_tier,
                )
                db.add(clone)
                db.flush()
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


def _collect_descendant_ids(
    db: Session, folder_id: uuid.UUID
) -> list[uuid.UUID]:
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
