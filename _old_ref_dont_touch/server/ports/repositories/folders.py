import uuid
from typing import Protocol

from infra.db.models import Folder


class FolderStore(Protocol):
    def get(self, folder_id: uuid.UUID) -> Folder: ...

    def add(self, folder: Folder) -> None: ...

    def save(self, folder: Folder) -> None: ...

    def delete(self, folder: Folder) -> None: ...

    def ensure_sibling_name_available(
        self,
        parent_id: uuid.UUID,
        name: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None: ...

    def collect_descendant_ids(self, folder_id: uuid.UUID) -> list[uuid.UUID]: ...

    def children_by_parent(self) -> dict[uuid.UUID, list[Folder]]: ...

    def delete_folders_by_ids(self, folder_ids: list[uuid.UUID]) -> None: ...
