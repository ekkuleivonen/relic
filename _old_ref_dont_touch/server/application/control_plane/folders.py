import uuid
from dataclasses import dataclass

from ports.entities import Folder


@dataclass(frozen=True)
class FolderResult:
    """A folder enriched with its resolved path and effective permissions for a user."""

    folder: Folder
    path: str
    effective_permissions: int
