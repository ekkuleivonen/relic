import uuid

from domain.exceptions import ConflictError
from infra.db.models import Blob, File
from ports.repositories.files import FileStore
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


class SqlAlchemyFileStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_name_available(self, folder_id: uuid.UUID, name: str) -> None:
        existing = self._session.scalar(
            select(File).where(File.folder_id == folder_id, File.name == name)
        )
        if existing is not None:
            raise ConflictError("File already exists")

    def save(self, file: File) -> None:
        self._session.flush()
        self._session.refresh(file)

    def ensure_blob_loaded(self, file: File) -> File:
        if file.blob is None:
            self._session.refresh(file, attribute_names=["blob"])
        return file

    def list_in_folders(self, folder_ids: list[uuid.UUID]) -> list[File]:
        if not folder_ids:
            return []
        return list(
            self._session.scalars(select(File).where(File.folder_id.in_(folder_ids))).all()
        )

    def delete_in_folders(self, folder_ids: list[uuid.UUID]) -> None:
        if not folder_ids:
            return
        self._session.execute(delete(File).where(File.folder_id.in_(folder_ids)))

    def add(self, file: File) -> None:
        self._session.add(file)
        self._session.flush()

    def delete(self, file: File) -> None:
        blob_id = file.blob_id
        self._session.delete(file)
        self._session.flush()
        if blob_id is not None:
            self.adjust_blob_refcounts({blob_id: -1})

    def adjust_blob_refcounts(self, deltas: dict[uuid.UUID, int]) -> None:
        for blob_id, delta in deltas.items():
            blob = self._session.get(Blob, blob_id)
            if blob is None:
                continue
            blob.refcount += delta
            if blob.refcount < 0:
                blob.refcount = 0


def build_file_store(session: Session) -> FileStore:
    return SqlAlchemyFileStore(session)
