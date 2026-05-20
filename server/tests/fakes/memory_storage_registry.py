"""In-memory storage registry for application-layer tests."""

import uuid

from infra.db.models import Bucket
from infra.object_storage.memory import MemoryObjectStorage
from ports.object_storage import ObjectStorage
from ports.storage_registry import StorageRegistry
from sqlalchemy.orm import Session


class MemoryStorageRegistry(StorageRegistry):
    def __init__(self) -> None:
        self.storage = MemoryObjectStorage()

    def for_bucket(self, bucket: Bucket) -> ObjectStorage:
        del bucket
        return self.storage

    def for_bucket_id(self, session: Session, bucket_id: uuid.UUID) -> ObjectStorage:
        del session, bucket_id
        return self.storage
