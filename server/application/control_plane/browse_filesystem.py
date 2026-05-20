"""Filesystem browse/list use cases (control plane)."""

import uuid

from application.uow import UnitOfWork
from infra.db.stores import filesystem
from infra.db.stores.filesystem import FileListPage, FolderStats
from ports.entities import Folder, User


def list_files(
    uow: UnitOfWork,
    current_user: User,
    *,
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
    limit: int,
    offset: int,
    sort: str,
    order: str,
) -> FileListPage:
    return filesystem.list_files(
        uow.session,
        current_user,
        folder_id=folder_id,
        recursive=recursive,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )


def get_folder_tree(
    uow: UnitOfWork,
    current_user: User,
    *,
    root_id: uuid.UUID | None = None,
) -> Folder:
    return filesystem.get_folder_tree(
        uow.session, current_user, root_id=root_id
    )


def get_folder_stats(
    uow: UnitOfWork,
    current_user: User,
    *,
    folder_id: uuid.UUID,
) -> FolderStats:
    return filesystem.get_folder_stats(
        uow.session, current_user, folder_id=folder_id
    )
