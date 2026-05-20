"""Effective folder permission inheritance."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from domain.filesystem.tree import FolderTreeNode, index_children


def compute_effective_permissions(
    nodes: Sequence[FolderTreeNode],
    grants_by_folder: Mapping[uuid.UUID, int],
    *,
    admin: bool,
    all_permissions: int,
) -> dict[uuid.UUID, int]:
    if admin:
        return {node.id: all_permissions for node in nodes}

    children_by_parent = index_children(nodes)
    permissions_by_folder: dict[uuid.UUID, int] = {}

    def walk(folder_id: uuid.UUID, inherited: int) -> None:
        permissions = inherited | grants_by_folder.get(folder_id, 0)
        permissions_by_folder[folder_id] = permissions
        for child_id in children_by_parent.get(folder_id, []):
            walk(child_id, permissions)

    for root_id in children_by_parent.get(None, []):
        walk(root_id, 0)

    return permissions_by_folder
