"""Resolve backing-store adapters per registered bucket."""

import uuid
from typing import Protocol

from infra.db.models import Bucket
from ports.object_storage import ObjectStorage
from sqlalchemy.orm import Session


class StorageRegistry(Protocol):
    def for_bucket(self, bucket: Bucket) -> ObjectStorage: ...

    def for_bucket_id(self, session: Session, bucket_id: uuid.UUID) -> ObjectStorage: ...
