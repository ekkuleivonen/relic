import uuid

from api.dependencies import AdminUser, CurrentUser, UnitOfWorkDep
from application.uow import UnitOfWork
from application.context import Actor, context_from_headers
from application.control_plane.storage_backend_mutations import (
    create_storage_backend as create_storage_backend_use_case,
    delete_storage_backend as delete_storage_backend_use_case,
    update_storage_backend as update_storage_backend_use_case,
)
from application.control_plane.create_folder import create_folder as create_folder_use_case
from application.control_plane.delete_folder import delete_folder as delete_folder_use_case
from application.control_plane.duplicate_folder import (
    duplicate_folder as duplicate_folder_use_case,
)
from application.control_plane.folders import FolderResult
from application.control_plane.grant_folder_access import (
    grant_folder_access as grant_folder_access_use_case,
    revoke_folder_access as revoke_folder_access_use_case,
)
from application.control_plane.update_folder import update_folder as update_folder_use_case
from enums import UserRole
from fastapi import APIRouter, Request, Response, status
from ports.entities import Folder, User
from pydantic import BaseModel, ConfigDict, Field
from application.control_plane import browse_filesystem
from application.control_plane.folder_placement import effective_preferred_storage_backend_id

router = APIRouter()

"""
Folder CRUD - the virtual filesystem.

Folders carry an optional ``preferred_storage_backend_id`` (admin-only). New uploads
under a folder land in the preferred bucket if it has capacity, else in the
hottest bucket per the latency-driven ranking. Inheritance walks ancestors
when the field is NULL.
"""


class FolderRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    path: str = Field(
        description=(
            "Full path from root (e.g. `photos/2024`). The first segment is the S3 "
            "gateway bucket name; remaining segments plus a filename form the object "
            "key (see `FileRead.gateway`)."
        ),
    )
    effective_permissions: int = Field(
        description="Caller permission bitfield: READ=1, WRITE=2, DELETE=4, ENRICH=8."
    )
    preferred_storage_backend_id: uuid.UUID | None = Field(
        default=None, description="Admin only: explicit storage backend preference."
    )
    effective_preferred_storage_backend_id: uuid.UUID | None = Field(
        default=None,
        description="Admin only: resolved backend after walking ancestors.",
    )

    @classmethod
    def from_result(
        cls,
        uow: UnitOfWork,
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
            preferred_storage_backend_id=result.folder.preferred_storage_backend_id,
            effective_preferred_storage_backend_id=effective_preferred_storage_backend_id(
                uow, result.folder
            ),
        )


class FolderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: uuid.UUID = Field(description="Parent folder UUID.")
    name: str = Field(min_length=1, max_length=255, description="New folder name.")


class FolderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = Field(default=None, description="Move folder under a new parent.")
    preferred_storage_backend_id: uuid.UUID | None = Field(
        default=None,
        description="Admin only: set preferred backend; null inherits from parent.",
    )


class FolderDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_parent_id: uuid.UUID = Field(description="Parent for the copy.")
    name: str = Field(min_length=1, max_length=255, description="Name for the copied folder.")
    recursive: bool = Field(
        default=True, description="Copy descendants when true."
    )


class FolderTreeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    path: str
    effective_permissions: int
    preferred_storage_backend_id: uuid.UUID | None = None
    effective_preferred_storage_backend_id: uuid.UUID | None = None
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
    uow: UnitOfWork,
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
                uow, child, include_storage_policy=include_storage_policy
            )
            for child in folder.tree_children
        ],
        preferred_storage_backend_id=(
            folder.preferred_storage_backend_id if include_storage_policy else None
        ),
        effective_preferred_storage_backend_id=(
            effective_preferred_storage_backend_id(uow, folder)
            if include_storage_policy
            else None
        ),
    )


@router.get("/tree", summary="Get folder tree")
async def get_folder_tree(
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
    root_id: uuid.UUID | None = None,
) -> FolderTreeRead:
    """
    Nested tree of visible folders for UI navigation.
    Query `root_id` to subtree from a specific folder.
    """
    root = browse_filesystem.get_folder_tree(uow, current_user, root_id=root_id)
    include_storage = current_user.role == UserRole.ADMIN
    return _folder_to_tree_read(uow, root, include_storage_policy=include_storage)


@router.get("/{folder_id}/stats", summary="Get folder stats")
async def get_folder_stats(
    folder_id: uuid.UUID,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> FolderStatsRead:
    """
    Recursive rollup: file counts, enrichment coverage, and logical size in bytes.
    Requires READ on the folder.
    """
    stats = browse_filesystem.get_folder_stats(
        uow, current_user, folder_id=folder_id
    )
    return FolderStatsRead(
        folder_id=stats.folder_id,
        file_count=stats.file_count,
        enriched_file_count=stats.enriched_file_count,
        logical_size_bytes=stats.logical_size_bytes,
        enrichment_coverage=stats.enrichment_coverage,
    )


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create folder")
async def create_folder(
    payload: FolderCreate,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> FolderRead:
    """Create a folder under `parent_id`. Caller needs WRITE on the parent."""
    result = create_folder_use_case(
        uow,
        actor=Actor.from_user(current_user),
        parent_id=payload.parent_id,
        name=payload.name,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return FolderRead.from_result(uow, result, user=current_user)


@router.patch("/{folder_id}", summary="Update folder")
async def update_folder(
    folder_id: uuid.UUID,
    payload: FolderUpdate,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> FolderRead:
    """Rename, move, and/or (admins) set preferred storage backend."""
    result = update_folder_use_case(
        uow,
        actor=Actor.from_user(current_user),
        folder_id=folder_id,
        name=payload.name,
        parent_id=payload.parent_id,
        preferred_storage_backend_id=payload.preferred_storage_backend_id,
        set_preferred_storage_backend_id="preferred_storage_backend_id" in payload.model_fields_set,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return FolderRead.from_result(uow, result, user=current_user)


@router.delete("/{folder_id}", summary="Delete folder")
async def delete_folder(
    folder_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
    recursive: bool = False,
) -> Response:
    """
    Delete a folder. Refuses if non-empty unless `recursive=true`.
    Cannot delete root.
    """
    delete_folder_use_case(
        uow,
        actor=Actor.from_user(current_user),
        folder_id=folder_id,
        recursive=recursive,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{folder_id}/copy", status_code=status.HTTP_201_CREATED, summary="Copy folder")
async def copy_folder(
    folder_id: uuid.UUID,
    payload: FolderDuplicate,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> FolderRead:
    """
    Metadata-only copy at a new location. No bytes moved; blob refcounts increment.
    Requires READ on source and WRITE on destination.
    """
    result = duplicate_folder_use_case(
        uow,
        actor=Actor.from_user(current_user),
        folder_id=folder_id,
        destination_parent_id=payload.destination_parent_id,
        name=payload.name,
        recursive=payload.recursive,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return FolderRead.from_result(uow, result, user=current_user)
