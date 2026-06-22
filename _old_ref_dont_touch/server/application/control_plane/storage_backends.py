"""StorageBackend read models — mutations use ``storage_backend_mutations`` on UoW."""

import uuid
from typing import Any

from application.uow import UnitOfWork
from ports.entities import StorageBackend
from infra.db.stores import storage_backend_reads

def list_storage_backends(uow: UnitOfWork) -> list[StorageBackend]:
    return storage_backend_reads.list_storage_backends(uow.session)


def list_storage_backend_reads(uow: UnitOfWork) -> list[dict[str, Any]]:
    return storage_backend_reads.list_storage_backend_reads(uow.session)


def get_storage_backend(uow: UnitOfWork, storage_backend_id: uuid.UUID) -> StorageBackend:
    return uow.storage_backends.get(storage_backend_id)


def get_storage_backend_read(uow: UnitOfWork, storage_backend_id: uuid.UUID) -> dict[str, Any]:
    return storage_backend_reads.get_storage_backend_read(uow.session, storage_backend_id)
