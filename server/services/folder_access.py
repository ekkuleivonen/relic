import uuid
from dataclasses import dataclass

import settings as S
from constants import FOLDER_ACCESS_ALL_PERMISSIONS, FOLDER_ACCESS_PERMISSION_MASK
from enums import Permission, UserRole
from domain.exceptions import BadRequestError, PermissionDenied, ResourceNotFound
from models import Folder, FolderAccess, User
from sqlalchemy import select
from sqlalchemy.orm import Session
from utils.logging import get_logger

from services.audit_events import create_audit_event
from services.event_context import EventContext
from services.s3_hotpath_cache import (
    TtlCacheEntry,
    engine_cache_key,
    get_or_set_request,
    get_ttl,
    request_cache,
    set_ttl,
)

log = get_logger(__name__)

_FOLDER_TREE_CACHE: dict[int, TtlCacheEntry] = {}
_FOLDER_PATHS_CACHE: dict[int, TtlCacheEntry] = {}
_EFFECTIVE_PERMISSIONS_CACHE: dict[tuple[int, uuid.UUID, int], TtlCacheEntry] = {}


@dataclass(frozen=True)
class FolderTreeRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str


@dataclass(frozen=True)
class FolderAccessRow:
    """A FolderAccess row enriched with the user object and the folder path."""

    access: FolderAccess
    user: User
    folder_path: str


def clear_hotpath_cache(db: Session | None = None) -> None:
    if db is None:
        _FOLDER_TREE_CACHE.clear()
        _FOLDER_PATHS_CACHE.clear()
        _EFFECTIVE_PERMISSIONS_CACHE.clear()
        return

    key = engine_cache_key(db)
    _FOLDER_TREE_CACHE.pop(key, None)
    _FOLDER_PATHS_CACHE.pop(key, None)
    for cache_key in list(_EFFECTIVE_PERMISSIONS_CACHE):
        if cache_key[0] == key:
            _EFFECTIVE_PERMISSIONS_CACHE.pop(cache_key, None)
    db.info.pop("s3_hotpath_cache", None)


def list_folder_access(db: Session) -> list[FolderAccessRow]:
    rows = list(
        db.execute(
            select(FolderAccess, User)
            .join(User, User.id == FolderAccess.actor_id)
            .order_by(User.email, FolderAccess.folder_id)
        ).all()
    )
    folder_ids = {row.FolderAccess.folder_id for row in rows}
    paths = compute_folder_paths(db, folder_ids)
    return [
        FolderAccessRow(
            access=row.FolderAccess,
            user=row.User,
            folder_path=paths[row.FolderAccess.folder_id],
        )
        for row in rows
    ]


def grant_folder_access(
    db: Session,
    *,
    actor_id: uuid.UUID,
    folder_id: uuid.UUID,
    permissions: int,
    event_context: EventContext | None = None,
) -> FolderAccessRow:
    """Insert or update an access grant. Idempotent on (actor_id, folder_id)."""
    validate_permissions(permissions)
    user = require_user(db, actor_id)
    folder = require_folder(db, folder_id)

    existing = db.scalar(
        select(FolderAccess).where(
            FolderAccess.actor_id == actor_id,
            FolderAccess.folder_id == folder_id,
        )
    )
    if existing:
        existing.permissions = int(permissions)
        access = existing
        action = "updated"
    else:
        access = FolderAccess(
            actor_id=actor_id,
            folder_id=folder_id,
            permissions=int(permissions),
        )
        db.add(access)
        action = "created"

    db.flush()
    folder_path = resolve_folder_path(db, folder)
    if event_context is not None:
        create_audit_event(
            db,
            operation="folder.access.updated" if existing else "folder.access.granted",
            actor_id=event_context.actor_id,
            request_id=event_context.request_id,
            metadata={
                "access_id": str(access.id),
                "actor_id": str(access.actor_id),
                "folder_id": str(access.folder_id),
                "permissions": access.permissions,
                "folder_path": folder_path,
            },
        )
    db.commit()
    db.refresh(access)
    clear_hotpath_cache(db)

    log.info(
        "folder_access_grant",
        action=action,
        actor_id=str(actor_id),
        folder_id=str(folder_id),
        permissions=int(permissions),
    )
    return FolderAccessRow(
        access=access,
        user=user,
        folder_path=folder_path,
    )


def revoke_folder_access(
    db: Session, access_id: uuid.UUID, *, event_context: EventContext | None = None
) -> None:
    access = db.get(FolderAccess, access_id)
    if not access:
        raise ResourceNotFound("Folder access grant not found")

    metadata = {
        "access_id": str(access.id),
        "actor_id": str(access.actor_id),
        "folder_id": str(access.folder_id),
        "permissions": access.permissions,
    }
    db.delete(access)
    if event_context is not None:
        create_audit_event(
            db,
            operation="folder.access.revoked",
            actor_id=event_context.actor_id,
            request_id=event_context.request_id,
            metadata=metadata,
        )
    db.commit()
    clear_hotpath_cache(db)
    log.info(
        "folder_access_revoke",
        access_id=str(access_id),
        actor_id=str(access.actor_id),
        folder_id=str(access.folder_id),
    )


def get_effective_permissions(
    db: Session, user: User, folder_id: uuid.UUID, *, use_cache: bool = True
) -> int:
    rows = cached_folder_tree_rows(db)
    if folder_id not in {row.id for row in rows}:
        raise ResourceNotFound("Folder not found")
    return effective_permissions_by_folder(db, user, use_cache=use_cache).get(
        folder_id, 0
    )


def require_folder_permission(
    db: Session,
    user: User,
    folder_id: uuid.UUID,
    required: Permission,
) -> int:
    permissions = get_effective_permissions(db, user, folder_id)
    if not permissions & int(required):
        raise ResourceNotFound("Folder not found")
    return permissions


def require_folder_permission_strict(
    db: Session,
    user: User,
    folder_id: uuid.UUID,
    required: Permission,
) -> int:
    """
    Like require_folder_permission, but distinguishes 404 vs 403.

    Returns 404 (ResourceNotFound) when the user can't READ the folder at all,
    so unreadable folders never leak existence. Returns 403 (PermissionDenied)
    when the user can READ but lacks the specific `required` bit.
    """
    permissions = get_effective_permissions(
        db,
        user,
        folder_id,
        use_cache=required == Permission.READ,
    )
    if not permissions & int(Permission.READ):
        raise ResourceNotFound("Folder not found")
    if not permissions & int(required):
        raise PermissionDenied("You do not have permission to perform this action")
    return permissions


def visible_folder_ids(db: Session, user: User) -> set[uuid.UUID]:
    folders = cached_folder_tree_rows(db)
    if user.role == UserRole.ADMIN:
        return {row.id for row in folders}

    children_by_parent: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for row in folders:
        children_by_parent.setdefault(row.parent_id, []).append(row.id)

    direct_grants = db.scalars(
        select(FolderAccess).where(FolderAccess.actor_id == user.id)
    ).all()
    visible: set[uuid.UUID] = set()
    queue = [
        grant.folder_id
        for grant in direct_grants
        if grant.permissions & int(Permission.READ)
    ]

    while queue:
        folder_id = queue.pop(0)
        if folder_id in visible:
            continue
        visible.add(folder_id)
        queue.extend(children_by_parent.get(folder_id, []))

    return visible


def filter_visible_tree(
    db: Session,
    user: User,
    *,
    root_id: uuid.UUID | None = None,
) -> Folder:
    root = get_tree_root(db, root_id)
    visible_ids = visible_folder_ids(db, user)
    if (
        root_id is not None
        and user.role != UserRole.ADMIN
        and root.id not in visible_ids
    ):
        raise ResourceNotFound("Root folder not found")

    permissions_by_folder = effective_permissions_by_folder(db, user)
    paths = compute_folder_paths(
        db,
        {
            folder_id
            for folder_id, _ in db.execute(select(Folder.id, Folder.parent_id)).all()
        },
    )
    folders = list(db.scalars(select(Folder).order_by(Folder.name)).all())
    children_by_parent: dict[uuid.UUID | None, list[Folder]] = {}
    for folder in folders:
        folder.path = paths[folder.id]
        children_by_parent.setdefault(folder.parent_id, []).append(folder)

    root.path = paths[root.id]
    root.effective_permissions = permissions_by_folder.get(root.id, 0)
    root.children = build_visible_children(
        root, children_by_parent, visible_ids, permissions_by_folder
    )
    return root


def effective_permissions_by_folder(
    db: Session,
    user: User,
    *,
    use_cache: bool = True,
) -> dict[uuid.UUID, int]:
    user_role = int(user.role)
    request_key = f"effective_permissions:{user.id}:{user_role}"
    cache = request_cache(db)
    if use_cache and request_key in cache:
        return cache[request_key]

    process_key = (engine_cache_key(db), user.id, user_role)
    cached = get_ttl(_EFFECTIVE_PERMISSIONS_CACHE, process_key) if use_cache else None
    if use_cache and cached is not None:
        cache[request_key] = cached
        return cached

    folders = cached_folder_tree_rows(db)
    if user.role == UserRole.ADMIN:
        permissions = {
            row.id: FOLDER_ACCESS_ALL_PERMISSIONS
            for row in folders
        }
        if use_cache:
            set_ttl(
                _EFFECTIVE_PERMISSIONS_CACHE,
                process_key,
                permissions,
                ttl_seconds=S.S3_HOTPATH_METADATA_CACHE_TTL_SECONDS,
            )
            cache[request_key] = permissions
        return permissions

    children_by_parent: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for row in folders:
        children_by_parent.setdefault(row.parent_id, []).append(row.id)

    grants_by_folder: dict[uuid.UUID, int] = {}
    grants = db.scalars(
        select(FolderAccess).where(FolderAccess.actor_id == user.id)
    ).all()
    for grant in grants:
        grants_by_folder[grant.folder_id] = (
            grants_by_folder.get(grant.folder_id, 0) | grant.permissions
        )

    permissions_by_folder: dict[uuid.UUID, int] = {}

    def walk(folder_id: uuid.UUID, inherited: int) -> None:
        permissions = inherited | grants_by_folder.get(folder_id, 0)
        permissions_by_folder[folder_id] = permissions
        for child_id in children_by_parent.get(folder_id, []):
            walk(child_id, permissions)

    for root_id in children_by_parent.get(None, []):
        walk(root_id, 0)

    if use_cache:
        set_ttl(
            _EFFECTIVE_PERMISSIONS_CACHE,
            process_key,
            permissions_by_folder,
            ttl_seconds=S.S3_HOTPATH_METADATA_CACHE_TTL_SECONDS,
        )
        cache[request_key] = permissions_by_folder
    return permissions_by_folder


def collect_ancestor_folder_ids(db: Session, folder_id: uuid.UUID) -> list[uuid.UUID]:
    request_key = f"ancestor_folder_ids:{folder_id}"
    return get_or_set_request(
        db,
        request_key,
        lambda: derive_ancestor_folder_ids(db, folder_id),
    )


def derive_ancestor_folder_ids(db: Session, folder_id: uuid.UUID) -> list[uuid.UUID]:
    rows = cached_folder_tree_rows(db)
    parent_by_folder = {row.id: row.parent_id for row in rows}
    if folder_id not in parent_by_folder:
        raise ResourceNotFound("Folder not found")
    ancestor_ids = [folder_id]
    cursor = parent_by_folder.get(folder_id)
    while cursor is not None:
        ancestor_ids.append(cursor)
        cursor = parent_by_folder.get(cursor)
    return ancestor_ids


def get_tree_root(db: Session, root_id: uuid.UUID | None) -> Folder:
    if root_id is not None:
        root = db.get(Folder, root_id)
    else:
        root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))

    if not root:
        raise ResourceNotFound("Root folder not found")

    return root


def build_visible_children(
    folder: Folder,
    children_by_parent: dict[uuid.UUID | None, list[Folder]],
    visible_ids: set[uuid.UUID],
    permissions_by_folder: dict[uuid.UUID, int],
) -> list[Folder]:
    visible_children: list[Folder] = []

    for child in sorted(
        children_by_parent.get(folder.id, []), key=lambda item: item.name
    ):
        child.effective_permissions = permissions_by_folder.get(child.id, 0)
        child.children = build_visible_children(
            child,
            children_by_parent,
            visible_ids,
            permissions_by_folder,
        )
        if child.id in visible_ids:
            visible_children.append(child)
        else:
            visible_children.extend(child.children)

    return visible_children


def validate_permissions(permissions: int) -> None:
    if permissions <= 0:
        raise BadRequestError("Permissions must include at least one capability")

    if permissions & ~int(FOLDER_ACCESS_PERMISSION_MASK):
        raise BadRequestError("Permissions contain unknown bits")

    has_read = bool(permissions & int(Permission.READ))
    needs_read = bool(
        permissions & int(Permission.WRITE | Permission.DELETE | Permission.ENRICH)
    )
    if needs_read and not has_read:
        raise BadRequestError("Write, delete, and enrich grants require read access")


def require_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ResourceNotFound("User not found")
    return user


def require_folder(db: Session, folder_id: uuid.UUID) -> Folder:
    folder = db.get(Folder, folder_id)
    if not folder:
        raise ResourceNotFound("Folder not found")
    return folder


def compute_folder_paths(
    db: Session, folder_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Resolve full paths for the given folder ids by walking the folder tree once."""
    if not folder_ids:
        return {}

    all_paths = cached_folder_paths(db)
    if not folder_ids.issubset(all_paths):
        clear_hotpath_cache(db)
        all_paths = cached_folder_paths(db)
    return {folder_id: all_paths[folder_id] for folder_id in folder_ids}


def cached_folder_tree_rows(db: Session) -> tuple[FolderTreeRow, ...]:
    request_key = "folder_tree_rows"
    cache = request_cache(db)
    if request_key in cache:
        return cache[request_key]

    key = engine_cache_key(db)
    cached = get_ttl(_FOLDER_TREE_CACHE, key)
    if cached is not None:
        cache[request_key] = cached
        return cached

    rows = tuple(
        FolderTreeRow(id=folder_id, parent_id=parent_id, name=name)
        for folder_id, parent_id, name in db.execute(
            select(Folder.id, Folder.parent_id, Folder.name)
        ).all()
    )
    set_ttl(
        _FOLDER_TREE_CACHE,
        key,
        rows,
        ttl_seconds=S.S3_HOTPATH_METADATA_CACHE_TTL_SECONDS,
    )
    cache[request_key] = rows
    return rows


def cached_folder_paths(db: Session) -> dict[uuid.UUID, str]:
    request_key = "folder_paths"
    cache = request_cache(db)
    if request_key in cache:
        return cache[request_key]

    key = engine_cache_key(db)
    cached = get_ttl(_FOLDER_PATHS_CACHE, key)
    if cached is not None:
        cache[request_key] = cached
        return cached

    paths = derive_folder_paths(db)
    set_ttl(
        _FOLDER_PATHS_CACHE,
        key,
        paths,
        ttl_seconds=S.S3_HOTPATH_METADATA_CACHE_TTL_SECONDS,
    )
    cache[request_key] = paths
    return paths


def derive_folder_paths(db: Session) -> dict[uuid.UUID, str]:
    rows = cached_folder_tree_rows(db)
    parent_of: dict[uuid.UUID, uuid.UUID | None] = {}
    name_of: dict[uuid.UUID, str] = {}
    for row in rows:
        parent_of[row.id] = row.parent_id
        name_of[row.id] = row.name

    cache: dict[uuid.UUID, str] = {}

    def path_for(folder_id: uuid.UUID) -> str:
        if folder_id in cache:
            return cache[folder_id]

        segments: list[str] = []
        cursor: uuid.UUID | None = folder_id
        while cursor is not None and cursor not in cache:
            segments.append(name_of[cursor])
            cursor = parent_of[cursor]

        prefix = cache[cursor] if cursor is not None else ""
        path = prefix
        for name in reversed(segments):
            path = format_path_segment(path, name)
        cache[folder_id] = path
        return path

    return {folder_id: path_for(folder_id) for folder_id in parent_of}


def resolve_folder_path(db: Session, folder: Folder) -> str:
    return compute_folder_paths(db, {folder.id})[folder.id]


def format_path_segment(prefix: str, name: str) -> str:
    """Compose a folder path. Root folder (empty name) renders as '/'."""
    if name == "":
        return "/"
    if prefix in ("", "/"):
        return f"/{name}"
    return f"{prefix}/{name}"
