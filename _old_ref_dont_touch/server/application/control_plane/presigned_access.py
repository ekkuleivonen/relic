"""Presigned URL helpers — resolve paths and permissions via UoW."""

import uuid

from application.context import Actor
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError
from enums import Permission
from infra.gateway import object_paths
from ports.entities import File, Folder

ROOT_FOLDER_UPLOAD_MESSAGE = (
    "Files must be uploaded into a subfolder, not the root folder."
)


def require_folder_for_write(
    uow: UnitOfWork, *, actor: Actor, folder_id: uuid.UUID
) -> Folder:
    folder = uow.permissions.require_folder(folder_id)
    uow.permissions.require_folder_permission(actor, folder.id, Permission.WRITE)
    return folder


def require_folder_accepts_files(folder: Folder) -> Folder:
    if folder.parent_id is None:
        raise BadRequestError(ROOT_FOLDER_UPLOAD_MESSAGE)
    return folder


def get_file_for_read(uow: UnitOfWork, *, actor: Actor, file_id: uuid.UUID) -> File:
    return uow.permissions.get_file_for_actor(actor, file_id, Permission.READ)


def get_file_for_delete(uow: UnitOfWork, *, actor: Actor, file_id: uuid.UUID) -> File:
    return uow.permissions.get_file_for_actor(actor, file_id, Permission.DELETE)


def bucket_and_key_for_file(uow: UnitOfWork, file: File) -> tuple[str, str]:
    return object_paths.build_bucket_and_key_for_file(uow.session, file)


def bucket_and_key_for_destination(
    uow: UnitOfWork, *, folder: Folder, filename: str
) -> tuple[str, str]:
    return object_paths.build_bucket_and_key_for_destination(
        uow.session, folder=folder, filename=filename
    )