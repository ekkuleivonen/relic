import uuid
from dataclasses import dataclass

from domain.filesystem.tree import FolderTreeNode
from infra.db.models import FolderAccess, User

FolderTreeRow = FolderTreeNode


@dataclass(frozen=True)
class FolderAccessRow:
    """A FolderAccess row enriched with the user object and the folder path."""

    access: FolderAccess
    user: User
    folder_path: str
