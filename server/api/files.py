import datetime as dt
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import CurrentUser
from database import DbSession
from services import files as files_service
from services import filesystem as filesystem_service
from services import parser_queue

router = APIRouter()

"""
File CRUD - the logical references inside folders.

Note: byte upload/download lives at the S3 gateway, not here. These routes
manage metadata records, queries, and atomic operations like move/rename.
"""


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    folder_id: uuid.UUID
    blob_id: uuid.UUID
    uploaded_by: uuid.UUID
    uploaded_by_name: str | None
    name: str
    parse_status: int
    meta: dict
    created_at: dt.datetime
    updated_at: dt.datetime


class MoveFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_folder_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=255)


class RenameFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)


@router.get("/")
async def list_files(
    db: DbSession,
    current_user: CurrentUser,
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
) -> list[FileRead]:
    return filesystem_service.list_files(
        db,
        current_user,
        folder_id=folder_id,
        recursive=recursive,
    )


@router.get("/{file_id}")
async def get_file(
    file_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> FileRead:
    return files_service.get_file(db, file_id, current_user)


@router.patch("/{file_id}")
async def rename_file(
    file_id: uuid.UUID,
    payload: RenameFileRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FileRead:
    """Rename a file in place and mark parser metadata stale."""
    file = files_service.rename_file(
        db,
        file_id=file_id,
        name=payload.name,
        current_user=current_user,
    )
    await parser_queue.enqueue_parse_file_best_effort(file.id)
    return file


@router.post("/{file_id}/move")
async def move_file(
    file_id: uuid.UUID,
    payload: MoveFileRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FileRead:
    """
    Move a file to another folder. Atomic; refcount on Blob unchanged.
    Parser metadata is marked stale only when the move also changes the name.
    """
    file = files_service.move_file(
        db,
        file_id=file_id,
        destination_folder_id=payload.destination_folder_id,
        name=payload.name,
        current_user=current_user,
    )
    if payload.name is not None:
        await parser_queue.enqueue_parse_file_best_effort(file.id)
    return file
