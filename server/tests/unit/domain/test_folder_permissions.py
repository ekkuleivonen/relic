import uuid

from constants import FOLDER_ACCESS_ALL_PERMISSIONS
from domain.filesystem.tree import (
    FolderTreeNode,
    collect_descendant_ids,
    index_children,
)
from domain.permissions.effective import compute_effective_permissions
from domain.permissions.grants import validate_folder_permissions
from domain.permissions.visibility import visible_folder_ids
from enums import Permission
import pytest
from domain.exceptions import BadRequestError


def _tree():
    root = uuid.uuid4()
    child = uuid.uuid4()
    grand = uuid.uuid4()
    return (
        [
            FolderTreeNode(id=root, parent_id=None, name=""),
            FolderTreeNode(id=child, parent_id=root, name="photos"),
            FolderTreeNode(id=grand, parent_id=child, name="2024"),
        ],
        root,
        child,
        grand,
    )


def test_validate_folder_permissions_requires_read_with_write():
    with pytest.raises(BadRequestError):
        validate_folder_permissions(int(Permission.WRITE))


def test_validate_folder_permissions_requires_read_with_delete():
    with pytest.raises(BadRequestError):
        validate_folder_permissions(int(Permission.DELETE))


def test_compute_effective_permissions_inherits_down_tree():
    nodes, root, child, grand = _tree()
    grants = {child: int(Permission.READ | Permission.WRITE)}

    perms = compute_effective_permissions(
        nodes,
        grants,
        admin=False,
        all_permissions=FOLDER_ACCESS_ALL_PERMISSIONS,
    )

    assert perms[root] == 0
    assert perms[child] == int(Permission.READ | Permission.WRITE)
    assert perms[grand] == int(Permission.READ | Permission.WRITE)


def test_visible_folder_ids_expands_read_grants_to_descendants():
    nodes, _root, child, grand = _tree()
    visible = visible_folder_ids(nodes, [child], is_admin=False)
    assert visible == {child, grand}


def test_collect_descendant_ids_can_include_or_exclude_root():
    nodes, root, child, grand = _tree()
    children = index_children(nodes)

    assert collect_descendant_ids(root, children, include_root=True) == [
        root,
        child,
        grand,
    ]
    assert collect_descendant_ids(root, children, include_root=False) == [
        child,
        grand,
    ]
