"""Pure folder tree helpers."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from domain.exceptions import ResourceNotFound


@dataclass(frozen=True)
class FolderTreeNode:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str


def index_children(
    nodes: Sequence[FolderTreeNode],
) -> dict[uuid.UUID | None, list[uuid.UUID]]:
    children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node.id)
    return children


def ancestor_folder_ids(
    folder_id: uuid.UUID,
    parent_by_folder: Mapping[uuid.UUID, uuid.UUID | None],
) -> list[uuid.UUID]:
    if folder_id not in parent_by_folder:
        raise ResourceNotFound("Folder not found")
    ancestor_ids = [folder_id]
    cursor = parent_by_folder.get(folder_id)
    while cursor is not None:
        ancestor_ids.append(cursor)
        cursor = parent_by_folder.get(cursor)
    return ancestor_ids


def descendant_folder_ids(
    read_grant_roots: Iterable[uuid.UUID],
    children_by_parent: Mapping[uuid.UUID | None, list[uuid.UUID]],
) -> set[uuid.UUID]:
    visible: set[uuid.UUID] = set()
    queue = list(read_grant_roots)
    while queue:
        folder_id = queue.pop(0)
        if folder_id in visible:
            continue
        visible.add(folder_id)
        queue.extend(children_by_parent.get(folder_id, []))
    return visible


def collect_descendant_ids(
    root_id: uuid.UUID,
    children_by_parent: Mapping[uuid.UUID | None, list[uuid.UUID]],
    *,
    include_root: bool,
) -> list[uuid.UUID]:
    folder_ids = [root_id] if include_root else []
    queue = list(children_by_parent.get(root_id, []))
    while queue:
        folder_id = queue.pop(0)
        folder_ids.append(folder_id)
        queue.extend(children_by_parent.get(folder_id, []))
    return folder_ids
