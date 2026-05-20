import uuid

from constants import FOLDER_ACCESS_ALL_PERMISSIONS
from domain.exceptions import PermissionDenied, ResourceNotFound
from domain.filesystem.tree import (
    ancestor_folder_ids,
    collect_descendant_ids,
    index_children,
)
from domain.permissions.effective import compute_effective_permissions
from domain.permissions.grants import validate_folder_permissions
from domain.permissions.visibility import visible_folder_ids as compute_visible_folder_ids
from enums import Permission, UserRole
from infra.cache.folder_access import (
    cached_folder_paths,
    cached_folder_tree_rows,
    clear_hotpath_cache,
    get_cached_effective_permissions,
    set_cached_effective_permissions,
)
from infra.cache.hotpath import get_or_set_request, request_cache
from infra.cache.scope import deployment_scope
from infra.db.models import Folder, FolderAccess, User
from infra.db.stores.audit_events import create_audit_event
from infra.db.stores.folder_access_types import FolderAccessRow, FolderTreeRow
from ports.context import EventContext
from sqlalchemy import select
from sqlalchemy.orm import Session
from utils.logging import get_logger

log = get_logger(__name__)


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
    validate_folder_permissions(permissions)
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
    db.refresh(access)

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
    db: Session,
    access_id: uuid.UUID,
    *,
    event_context: EventContext | None = None,
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
        return compute_visible_folder_ids(folders, [], is_admin=True)

    direct_grants = db.scalars(
        select(FolderAccess).where(FolderAccess.actor_id == user.id)
    ).all()
    read_roots = [
        grant.folder_id
        for grant in direct_grants
        if grant.permissions & int(Permission.READ)
    ]
    return compute_visible_folder_ids(folders, read_roots, is_admin=False)


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
    tree_rows = cached_folder_tree_rows(db)
    children_by_id = index_children(tree_rows)
    subtree_ids = set(
        collect_descendant_ids(root.id, children_by_id, include_root=True)
    )
    parent_by_folder = {row.id: row.parent_id for row in tree_rows}
    needed_ids = _folders_needed_for_visible_tree(
        root_id=root.id,
        subtree_ids=subtree_ids,
        visible_ids=visible_ids,
        parent_by_folder=parent_by_folder,
    )
    paths = compute_folder_paths(db, needed_ids)
    folders = list(
        db.scalars(
            select(Folder).where(Folder.id.in_(needed_ids)).order_by(Folder.name)
        ).all()
    )
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


def _folders_needed_for_visible_tree(
    *,
    root_id: uuid.UUID,
    subtree_ids: set[uuid.UUID],
    visible_ids: set[uuid.UUID],
    parent_by_folder: dict[uuid.UUID, uuid.UUID | None],
) -> set[uuid.UUID]:
    needed = {root_id}
    for visible_id in visible_ids & subtree_ids:
        cursor: uuid.UUID | None = visible_id
        while cursor is not None and cursor in subtree_ids and cursor not in needed:
            needed.add(cursor)
            if cursor == root_id:
                break
            cursor = parent_by_folder.get(cursor)
    return needed


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

    process_key = (deployment_scope(), user.id, user_role)
    cached = get_cached_effective_permissions(process_key) if use_cache else None
    if use_cache and cached is not None:
        cache[request_key] = cached
        return cached

    folders = cached_folder_tree_rows(db)
    if user.role == UserRole.ADMIN:
        permissions = compute_effective_permissions(
            folders,
            {},
            admin=True,
            all_permissions=FOLDER_ACCESS_ALL_PERMISSIONS,
        )
        if use_cache:
            set_cached_effective_permissions(process_key, permissions)
            cache[request_key] = permissions
        return permissions

    grants_by_folder: dict[uuid.UUID, int] = {}
    grants = db.scalars(
        select(FolderAccess).where(FolderAccess.actor_id == user.id)
    ).all()
    for grant in grants:
        grants_by_folder[grant.folder_id] = (
            grants_by_folder.get(grant.folder_id, 0) | grant.permissions
        )

    permissions_by_folder = compute_effective_permissions(
        folders,
        grants_by_folder,
        admin=False,
        all_permissions=FOLDER_ACCESS_ALL_PERMISSIONS,
    )

    if use_cache:
        set_cached_effective_permissions(process_key, permissions_by_folder)
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
    return ancestor_folder_ids(folder_id, parent_by_folder)


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
    if not folder_ids:
        return {}

    all_paths = cached_folder_paths(db)
    if not folder_ids.issubset(all_paths):
        clear_hotpath_cache(db)
        all_paths = cached_folder_paths(db)
    return {folder_id: all_paths[folder_id] for folder_id in folder_ids}


def resolve_folder_path(db: Session, folder: Folder) -> str:
    return compute_folder_paths(db, {folder.id})[folder.id]
