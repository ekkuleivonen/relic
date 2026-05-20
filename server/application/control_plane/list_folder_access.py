"""Folder ACL listing (control plane)."""

from application.uow import UnitOfWork
from infra.db.stores import folder_access
from infra.db.stores.folder_access_types import FolderAccessRow


def list_folder_access(uow: UnitOfWork) -> list[FolderAccessRow]:
    return folder_access.list_folder_access(uow.session)
