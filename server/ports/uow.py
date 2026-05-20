"""Unit-of-work boundary shared by application use cases and infra jobs."""

from typing import Protocol

from ports.audit import AuditPort
from ports.cache import CachePort
from ports.repositories.access_keys import AccessKeyStore
from ports.repositories.blobs import BlobStore
from ports.repositories.storage_backends import StorageBackendStore
from ports.repositories.files import FileStore
from ports.repositories.folders import FolderStore
from ports.repositories.multipart import MultipartStore
from ports.repositories.permissions import PermissionStore
from ports.repositories.search import SearchStore
from ports.repositories.users import UserStore
from ports.storage_registry import StorageRegistry
from sqlalchemy.orm import Session


class UnitOfWork(Protocol):
    session: Session
    files: FileStore
    folders: FolderStore
    storage_backends: StorageBackendStore
    blobs: BlobStore
    users: UserStore
    access_keys: AccessKeyStore
    permissions: PermissionStore
    search: SearchStore
    multipart: MultipartStore
    cache: CachePort
    audit: AuditPort
    storage: StorageRegistry

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...
