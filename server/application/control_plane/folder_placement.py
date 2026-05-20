"""StorageBackend placement queries for control-plane responses."""

from application.uow import UnitOfWork
from infra.db.stores.placement import effective_preferred_storage_backend_id as _effective
from ports.entities import Folder


def effective_preferred_storage_backend_id(uow: UnitOfWork, folder: Folder):
    return _effective(uow.session, folder)
