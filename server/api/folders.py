import uuid

from database import DbSession
from enums import UserRole
from fastapi import APIRouter, Request, Response, status
from models import Folder, User
from pydantic import BaseModel, ConfigDict, Field
from services import filesystem as filesystem_service
from services import folders as folders_service
from services.event_context import context_from_headers
from services.folders import FolderResult
from services.placement import effective_preferred_bucket_id

from api.dependencies import CurrentUser

router = APIRouter()

"""
Folder CRUD - the virtual filesystem.

Folders carry an optional ``preferred_bucket_id`` (admin-only). New uploads
under a folder land in the preferred bucket if it has capacity, else in the
hottest bucket per the latency-driven ranking. Inheritance walks ancestors
when the field is NULL.
"""


class FolderRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    path: str
    effective_permissions: int
    preferred_bucket_id: uuid.UUID | None = None
    effective_preferred_bucket_id: uuid.UUID | None = None

    @classmethod
    def from_result(
        cls,
        db: DbSession,
        result: FolderResult,
        *,
        user: User,
    ) -> "FolderRead":
        show = user.role == UserRole.ADMIN
        if not show:
            return cls(
                id=result.folder.id,
                parent_id=result.folder.parent_id,
                name=result.folder.name,
                path=result.path,
                effective_permissions=result.effective_permissions,
            )
        return cls(
            id=result.folder.id,
            parent_id=result.folder.parent_id,
            name=result.folder.name,
            path=result.path,
            effective_permissions=result.effective_permissions,
            preferred_bucket_id=result.folder.preferred_bucket_id,
            effective_preferred_bucket_id=effective_preferred_bucket_id(
                db, result.folder
            ),
        )


class FolderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)


class FolderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    preferred_bucket_id: uuid.UUID | None = None


class FolderDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_parent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    recursive: bool = True


class FolderTreeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    path: str
    effective_permissions: int
    preferred_bucket_id: uuid.UUID | None = None
    effective_preferred_bucket_id: uuid.UUID | None = None
    children: list["FolderTreeRead"]


class FolderStatsRead(BaseModel):
    """Recursive rollup over a folder and all of its descendants."""

    model_config = ConfigDict(extra="forbid")

    folder_id: uuid.UUID
    file_count: int
    enriched_file_count: int
    logical_size_bytes: int
    enrichment_coverage: float | None


def _folder_to_tree_read(
    db: DbSession,
    folder: Folder,
    *,
    include_storage_policy: bool,
) -> FolderTreeRead:
    return FolderTreeRead(
        id=folder.id,
        name=folder.name,
        parent_id=folder.parent_id,
        path=folder.path,
        effective_permissions=folder.effective_permissions,
        children=[
            _folder_to_tree_read(
                db, child, include_storage_policy=include_storage_policy
            )
            for child in folder.children
        ],
        preferred_bucket_id=(
            folder.preferred_bucket_id if include_storage_policy else None
        ),
        effective_preferred_bucket_id=(
            effective_preferred_bucket_id(db, folder)
            if include_storage_policy
            else None
        ),
    )


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
    root = filesystem_service.get_folder_tree(db, current_user, root_id)
    include_storage = current_user.role == UserRole.ADMIN
    return _folder_to_tree_read(db, root, include_storage_policy=include_storage)


@router.get("/{folder_id}/stats")
async def get_folder_stats(
    folder_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> FolderStatsRead:
    """
    GET /folders/{id}/stats -> recursive rollup over this folder + descendants.
    Returns total file count, enriched (file_info section completed) count, and
    logical size in bytes (sum of blob sizes per file row, no dedupe).
    Caller needs READ on the folder.
    """
    stats = filesystem_service.get_folder_stats(
        db, current_user, folder_id=folder_id
    )
    return FolderStatsRead(
        folder_id=stats.folder_id,
        file_count=stats.file_count,
        enriched_file_count=stats.enriched_file_count,
        logical_size_bytes=stats.logical_size_bytes,
        enrichment_coverage=stats.enrichment_coverage,
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: FolderCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> FolderRead:
    """
    POST /folders -> create a new folder under `parent_id`.
    Body: { parent_id, name }
    New folders inherit the ancestor preferred_bucket_id.
    Caller needs WRITE on the parent.
    """
    result = folders_service.create_folder(
        db,
        current_user,
        parent_id=payload.parent_id,
        name=payload.name,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return FolderRead.from_result(db, result, user=current_user)


@router.patch("/{folder_id}")
async def update_folder(
    folder_id: uuid.UUID,
    payload: FolderUpdate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> FolderRead:
    """
    PATCH /folders/{id} -> rename, move, and/or (admins) preferred bucket.
    Body: { name?, parent_id?, preferred_bucket_id? }
    Set preferred_bucket_id to null to inherit from a parent.
    """
    result = folders_service.update_folder(
        db,
        current_user,
        folder_id=folder_id,
        name=payload.name,
        parent_id=payload.parent_id,
        preferred_bucket_id=payload.preferred_bucket_id,
        set_preferred_bucket_id="preferred_bucket_id" in payload.model_fields_set,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return FolderRead.from_result(db, result, user=current_user)


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    recursive: bool = False,
) -> Response:
    """
    DELETE /folders/{id} -> delete folder.
    Refuses if folder has files or subfolders unless ?recursive=true.
    Recursive delete removes files and decrements refcounts on referenced blobs;
    refcount-zero blobs are purged asynchronously by the storage maintenance worker (arq cron).
    Cannot delete root.
    """
    folders_service.delete_folder(
        db,
        current_user,
        folder_id=folder_id,
        recursive=recursive,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{folder_id}/copy", status_code=status.HTTP_201_CREATED)
async def copy_folder(
    folder_id: uuid.UUID,
    payload: FolderDuplicate,
    request: Request,
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
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return FolderRead.from_result(db, result, user=current_user)
