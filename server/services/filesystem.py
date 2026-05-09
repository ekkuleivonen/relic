import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import BigInteger, asc, cast, desc, func, nullslast, select
from sqlalchemy.orm import Session

from managers.exceptions import BadRequestError, ResourceNotFound
from models import File, Folder, User
from schema_plan import Permission
from services import folder_access as folder_access_service

DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200
LIST_SORT_FIELDS = frozenset({"name", "updated_at", "size", "mimetype"})
LIST_SORT_ORDERS = frozenset({"asc", "desc"})


@dataclass(frozen=True)
class FileListPage:
    items: list[File]
    total: int


def get_folder_tree(
    db: Session,
    current_user: User,
    root_id: uuid.UUID | None = None,
) -> Folder:
    return folder_access_service.filter_visible_tree(
        db,
        current_user,
        root_id=root_id,
    )


def _validate_list_files_params(*, limit: int, offset: int, sort: str, order: str) -> None:
    if limit < 1 or limit > MAX_LIST_LIMIT:
        raise BadRequestError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
    if offset < 0:
        raise BadRequestError("offset must be >= 0")
    if sort not in LIST_SORT_FIELDS:
        raise BadRequestError(f"sort must be one of {sorted(LIST_SORT_FIELDS)}")
    if order not in LIST_SORT_ORDERS:
        raise BadRequestError("order must be 'asc' or 'desc'")


def _list_files_order_by(sort: str, order: str):
    order_asc = order == "asc"
    primary = asc if order_asc else desc
    tie = asc(File.id) if order_asc else desc(File.id)

    if sort == "name":
        return primary(File.name), tie
    if sort == "updated_at":
        return primary(File.updated_at), tie
    if sort == "mimetype":
        col = File.meta["mimetype"].as_string()
        return nullslast(primary(col)), tie
    if sort == "size":
        col = cast(File.meta["size"].as_string(), BigInteger)
        return nullslast(primary(col)), tie
    raise BadRequestError(f"unsupported sort {sort!r}")


def list_files(
    db: Session,
    current_user: User,
    *,
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
    limit: int = DEFAULT_LIST_LIMIT,
    offset: int = 0,
    sort: str = "name",
    order: str = "asc",
) -> FileListPage:
    _validate_list_files_params(limit=limit, offset=offset, sort=sort, order=order)

    if folder_id is None:
        visible_ids = folder_access_service.visible_folder_ids(db, current_user)
        if not visible_ids:
            return FileListPage(items=[], total=0)
        filters = [File.folder_id.in_(visible_ids)]
    else:
        folder = db.get(Folder, folder_id)
        if not folder:
            raise ResourceNotFound("Folder not found")
        folder_access_service.require_folder_permission(
            db,
            current_user,
            folder_id,
            Permission.READ,
        )

        if recursive:
            descendant_ids = collect_descendant_folder_ids(db, folder_id)
            visible_ids = folder_access_service.visible_folder_ids(db, current_user)
            scoped = [fid for fid in descendant_ids if fid in visible_ids]
            if not scoped:
                return FileListPage(items=[], total=0)
            filters = [File.folder_id.in_(scoped)]
        else:
            filters = [File.folder_id == folder_id]

    count_stmt = select(func.count()).select_from(File).where(*filters)
    total = db.scalar(count_stmt) or 0

    order_parts = _list_files_order_by(sort, order)
    page_stmt = (
        select(File).where(*filters).order_by(*order_parts).limit(limit).offset(offset)
    )
    items = list(db.scalars(page_stmt).all())
    return FileListPage(items=items, total=total)


def get_tree_root(db: Session, root_id: uuid.UUID | None) -> Folder:
    if root_id is not None:
        root = db.get(Folder, root_id)
    else:
        root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))

    if not root:
        raise ResourceNotFound("Root folder not found")

    return root


def attach_children(
    folder: Folder,
    children_by_parent: dict[uuid.UUID | None, list[Folder]],
) -> None:
    children = children_by_parent.get(folder.id, [])
    folder.children = sorted(children, key=lambda child: child.name)

    for child in folder.children:
        attach_children(child, children_by_parent)


def collect_descendant_folder_ids(db: Session, folder_id: uuid.UUID) -> list[uuid.UUID]:
    folders = db.execute(select(Folder.id, Folder.parent_id)).all()
    children_by_parent: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)

    for child_id, parent_id in folders:
        children_by_parent[parent_id].append(child_id)

    folder_ids = [folder_id]
    queue = [folder_id]

    while queue:
        parent_id = queue.pop(0)
        child_ids = children_by_parent.get(parent_id, [])
        folder_ids.extend(child_ids)
        queue.extend(child_ids)

    return folder_ids
