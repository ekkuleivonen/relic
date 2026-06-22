import datetime as dt
import uuid
from typing import Any

from domain.exceptions import ConflictError, ResourceNotFound
from infra.db.models import Blob, StorageBackend, StorageBackendProbe
from ports.repositories.storage_backends import StorageBackendStore
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session


class SqlAlchemyStorageBackendStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, storage_backend_id: uuid.UUID) -> StorageBackend:
        bucket = self._session.get(StorageBackend, storage_backend_id)
        if bucket is None:
            raise ResourceNotFound("Storage backend not found")
        return bucket

    def ensure_name_available(
        self, name: str, *, excluding_id: uuid.UUID | None = None
    ) -> None:
        query = select(StorageBackend).where(StorageBackend.name == name)
        if excluding_id is not None:
            query = query.where(StorageBackend.id != excluding_id)
        if self._session.scalar(query) is not None:
            raise ConflictError("A storage backend with this name already exists")

    def add(self, bucket: StorageBackend) -> None:
        self._session.add(bucket)
        self._session.flush()

    def apply_updates(self, bucket: StorageBackend, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(bucket, key, value)
        self._session.flush()

    def delete(self, bucket: StorageBackend) -> None:
        self._session.delete(bucket)

    def blob_count(self, storage_backend_id: uuid.UUID) -> int:
        count = self._session.scalar(
            select(func.count()).select_from(Blob).where(Blob.storage_backend_id == storage_backend_id)
        )
        return int(count or 0)

    def add_probe(self, probe: StorageBackendProbe) -> None:
        self._session.add(probe)
        self._session.flush()

    def delete_probes_older_than(self, cutoff: dt.datetime) -> int:
        result = self._session.execute(
            delete(StorageBackendProbe).where(StorageBackendProbe.observed_at < cutoff)
        )
        return int(result.rowcount or 0)

    def refresh(self, *entities: object) -> None:
        for entity in entities:
            self._session.refresh(entity)


def build_storage_backend_store(session: Session) -> StorageBackendStore:
    return SqlAlchemyStorageBackendStore(session)
