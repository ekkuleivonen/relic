import uuid

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import CurrentUser
from database import DbSession
from services import filesystem as filesystem_service
from services import folders as folders_service
from services.folders import FolderResult

router = APIRouter()

"""
Folder CRUD - the virtual filesystem.

Most user-facing operations: browsing, creating subfolders, and managing
per-folder cooldown policies.
"""


class FolderRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    path: str
    effective_permissions: int

    @classmethod
    def from_result(cls, result: FolderResult) -> "FolderRead":
        return cls(
            id=result.folder.id,
            parent_id=result.folder.parent_id,
            name=result.folder.name,
            path=result.path,
            effective_permissions=result.effective_permissions,
        )


class FolderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)


class FolderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class FolderDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_parent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    recursive: bool = True


class FolderTreeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    path: str
    effective_permissions: int
    children: list["FolderTreeRead"]


@router.get("/tree")
async def get_folder_tree(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    root_id: uuid.UUID | None = None,
) -> FolderTreeRead:
    """
    GET /folders/tree -> nested tree of all visible folders.
    Convenience for UI navigation; equivalent to walking list_folders.
    Query params: ?root_id=<uuid> to subtree from a specific folder.
    """
    return filesystem_service.get_folder_tree(db, current_user, root_id)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: FolderCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> FolderRead:
    """
    POST /folders -> create a new folder under `parent_id`.
    Body: { parent_id, name }
    Cooldown and min_tier are inherited from the parent. Caller needs WRITE
    on the parent.
    """
    result = folders_service.create_folder(
        db,
        current_user,
        parent_id=payload.parent_id,
        name=payload.name,
    )
    return FolderRead.from_result(result)


@router.patch("/{folder_id}")
async def update_folder(
    folder_id: uuid.UUID,
    payload: FolderUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> FolderRead:
    """
    PATCH /folders/{id} -> rename and/or move.
    Body: { name?, parent_id? }
    Caller needs WRITE on the folder, plus WRITE on the new parent when moving.
    Cycles (moving a folder into a descendant) are rejected.
    """
    result = folders_service.update_folder(
        db,
        current_user,
        folder_id=folder_id,
        name=payload.name,
        parent_id=payload.parent_id,
    )
    return FolderRead.from_result(result)


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    recursive: bool = False,
) -> Response:
    """
    DELETE /folders/{id} -> delete folder.
    Refuses if folder has files or subfolders unless ?recursive=true.
    Recursive delete decrements refcounts on all referenced blobs;
    blobs hitting refcount 0 are GC'd.
    Cannot delete root.
    """
    folders_service.delete_folder(
        db,
        current_user,
        folder_id=folder_id,
        recursive=recursive,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{folder_id}/copy", status_code=status.HTTP_201_CREATED)
async def copy_folder(
    folder_id: uuid.UUID,
    payload: FolderDuplicate,
    db: DbSession,
    current_user: CurrentUser,
) -> FolderRead:
    """
    POST /folders/{id}/copy -> create a metadata-only copy of the folder
    (and, by default, all its descendants) at a new location.
    Body: { destination_parent_id, name, recursive?: bool = true }
    No bytes moved; refcounts on referenced blobs are incremented.
    Caller needs READ on source and WRITE on destination.
    """
    result = folders_service.duplicate_folder(
        db,
        current_user,
        folder_id=folder_id,
        destination_parent_id=payload.destination_parent_id,
        name=payload.name,
        recursive=payload.recursive,
    )
    return FolderRead.from_result(result)
