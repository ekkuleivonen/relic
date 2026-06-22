"""Shared folder use-case helpers."""

from application.context import Actor
from application.control_plane.folders import FolderResult
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError
from ports.entities import Folder


def validate_folder_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise BadRequestError("Folder name cannot be empty")
    if "/" in cleaned:
        raise BadRequestError("Folder name cannot contain '/'")
    return cleaned


def folder_result(uow: UnitOfWork, actor: Actor, folder: Folder) -> FolderResult:
    return FolderResult(
        folder=folder,
        path=uow.permissions.resolve_folder_path(folder),
        effective_permissions=uow.permissions.effective_permissions(actor, folder.id),
    )
