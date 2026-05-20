"""Resolve backing-store adapters per registered bucket."""

import uuid
from typing import Protocol

from infra.db.models import StorageBackend
from ports.object_storage import ObjectStorage
from sqlalchemy.orm import Session


class StorageRegistry(Protocol):
    def for_storage_backend(self, bucket: StorageBackend) -> ObjectStorage: ...

    def for_storage_backend_id(self, session: Session, storage_backend_id: uuid.UUID) -> ObjectStorage: ...
