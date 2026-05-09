import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from managers.exceptions import ResourceNotFound
from models import File, Folder


def get_folder_tree(db: Session, root_id: uuid.UUID | None = None) -> Folder:
    root = get_tree_root(db, root_id)
    folders = db.scalars(select(Folder).order_by(Folder.name)).all()
    children_by_parent: dict[uuid.UUID | None, list[Folder]] = defaultdict(list)

    for folder in folders:
        children_by_parent[folder.parent_id].append(folder)

    attach_children(root, children_by_parent)
    return root


def list_files(
    db: Session,
    *,
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
) -> list[File]:
    query = select(File).order_by(File.name)

    if folder_id is None:
        return list(db.scalars(query).all())

    folder = db.get(Folder, folder_id)
    if not folder:
        raise ResourceNotFound("Folder not found")

    if recursive:
        folder_ids = collect_descendant_folder_ids(db, folder_id)
        return list(db.scalars(query.where(File.folder_id.in_(folder_ids))).all())

    return list(db.scalars(query.where(File.folder_id == folder_id)).all())


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
