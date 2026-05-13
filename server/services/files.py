"""Control-plane file operations: move and rename.

Move and rename are pure metadata operations on the File row. They live in
the control plane (not the gateway) because they're atomic database
transactions that don't move bytes — see `api-split.md`.
"""

import os
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from managers.exceptions import BadRequestError
from models import File, PARSE_STATUS_PENDING, User
from schema_plan import Permission
from services import folder_access as folder_access_service
from services import objects as object_service


def _with_preserved_extension(original_filename: str, new_filename: str) -> str:
    """If *new_filename* has no extension, append *original_filename*'s extension."""
    _, old_ext = os.path.splitext(original_filename)
    _, new_ext = os.path.splitext(new_filename)
    if new_ext or not old_ext:
        return new_filename
    return f"{new_filename}{old_ext}"


def _normalize_requested_file_name(*, current_name: str, requested_name: str) -> str:
    name = requested_name.strip()
    validate_filename(name)
    name = _with_preserved_extension(current_name, name)
    validate_filename(name)
    return name


def move_file(
    db: Session,
    *,
    file_id: uuid.UUID,
    destination_folder_id: uuid.UUID,
    name: str | None,
    current_user: User,
) -> File:
    file = object_service.get_file_for_user(
        db, file_id, current_user, Permission.DELETE
    )
    destination = folder_access_service.require_folder(db, destination_folder_id)
    folder_access_service.require_folder_permission_strict(
        db, current_user, destination.id, Permission.WRITE
    )

    if name is not None:
        new_name = _normalize_requested_file_name(
            current_name=file.name, requested_name=name
        )
    else:
        new_name = file.name
        validate_filename(new_name)

    if file.folder_id == destination.id and file.name == new_name:
        return file

    object_service.ensure_file_name_available(db, destination.id, new_name)

    file.folder_id = destination.id
    file.name = new_name
    if name is not None:
        file.parse_status = PARSE_STATUS_PENDING
    db.flush()
    db.commit()
    db.refresh(file)
    return file


def rename_file(
    db: Session,
    *,
    file_id: uuid.UUID,
    name: str,
    current_user: User,
) -> File:
    file = object_service.get_file_for_user(
        db, file_id, current_user, Permission.WRITE
    )
    name = _normalize_requested_file_name(
        current_name=file.name, requested_name=name
    )

    if file.name == name:
        return file

    object_service.ensure_file_name_available(db, file.folder_id, name)

    file.name = name
    file.parse_status = PARSE_STATUS_PENDING
    db.flush()
    db.commit()
    db.refresh(file)
    return file


def get_file(db: Session, file_id: uuid.UUID, current_user: User) -> File:
    return object_service.get_file_for_user(
        db, file_id, current_user, Permission.READ
    )


def list_files_in_folder(db: Session, folder_id: uuid.UUID) -> list[File]:
    return list(
        db.scalars(
            select(File).where(File.folder_id == folder_id).order_by(File.name)
        ).all()
    )


def validate_filename(name: str) -> None:
    if not name or not name.strip():
        raise BadRequestError("Filename cannot be empty")
    if "/" in name:
        raise BadRequestError("Filename cannot contain '/'")
    if len(name) > 255:
        raise BadRequestError("Filename is too long")
