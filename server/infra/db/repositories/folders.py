import uuid
from collections import defaultdict

from domain.exceptions import ConflictError, ResourceNotFound
from infra.db.models import Folder
from ports.repositories.folders import FolderStore
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class SqlAlchemyFolderStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, folder_id: uuid.UUID) -> Folder:
        folder = self._session.get(Folder, folder_id)
        if folder is None:
            raise ResourceNotFound("Folder not found")
        return folder

    def add(self, folder: Folder) -> None:
        self._session.add(folder)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("A folder with that name already exists here.") from exc

    def save(self, folder: Folder) -> None:
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("A folder with that name already exists here.") from exc
        self._session.refresh(folder)

    def delete(self, folder: Folder) -> None:
        self._session.delete(folder)

    def ensure_sibling_name_available(
        self,
        parent_id: uuid.UUID,
        name: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        query = select(Folder).where(
            Folder.parent_id == parent_id,
            Folder.name == name,
        )
        if exclude_id is not None:
            query = query.where(Folder.id != exclude_id)
        if self._session.scalar(query) is not None:
            raise ConflictError("A folder with that name already exists here.")

    def collect_descendant_ids(self, folder_id: uuid.UUID) -> list[uuid.UUID]:
        rows = self._session.execute(select(Folder.id, Folder.parent_id)).all()
        children_by_parent: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
        for child_id, parent_id in rows:
            children_by_parent[parent_id].append(child_id)

        descendants: list[uuid.UUID] = []
        queue = list(children_by_parent.get(folder_id, []))
        while queue:
            current = queue.pop(0)
            descendants.append(current)
            queue.extend(children_by_parent.get(current, []))
        return descendants

    def children_by_parent(self) -> dict[uuid.UUID, list[Folder]]:
        folders = list(
            self._session.scalars(select(Folder).order_by(Folder.name)).all()
        )
        by_parent: dict[uuid.UUID, list[Folder]] = defaultdict(list)
        for folder in folders:
            if folder.parent_id is not None:
                by_parent[folder.parent_id].append(folder)
        return by_parent

    def delete_folders_by_ids(self, folder_ids: list[uuid.UUID]) -> None:
        if not folder_ids:
            return
        self._session.execute(delete(Folder).where(Folder.id.in_(folder_ids)))


def build_folder_store(session: Session) -> FolderStore:
    return SqlAlchemyFolderStore(session)
