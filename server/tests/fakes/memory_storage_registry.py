"""In-memory storage registry for application-layer tests."""

import uuid

from infra.db.models import StorageBackend
from infra.object_storage.memory import MemoryObjectStorage
from ports.object_storage import ObjectStorage
from ports.storage_registry import StorageRegistry
from sqlalchemy.orm import Session


class MemoryStorageRegistry(StorageRegistry):
    def __init__(self) -> None:
        self.storage = MemoryObjectStorage()

    def for_storage_backend(self, bucket: StorageBackend) -> ObjectStorage:
        del bucket
        return self.storage

    def for_storage_backend_id(self, session: Session, storage_backend_id: uuid.UUID) -> ObjectStorage:
        del session, storage_backend_id
        return self.storage
