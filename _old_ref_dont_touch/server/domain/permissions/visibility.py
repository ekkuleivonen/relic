"""Folder visibility from read grants."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from domain.filesystem.tree import FolderTreeNode, descendant_folder_ids, index_children


def visible_folder_ids(
    nodes: Sequence[FolderTreeNode],
    read_grant_roots: Iterable[uuid.UUID],
    *,
    is_admin: bool,
) -> set[uuid.UUID]:
    if is_admin:
        return {node.id for node in nodes}

    children_by_parent = index_children(nodes)
    return descendant_folder_ids(read_grant_roots, children_by_parent)
