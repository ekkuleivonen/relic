import uuid

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.dependencies import CurrentUser
from database import DbSession
from models import Folder, User
from schema_plan import UserRole
from services import filesystem as filesystem_service
from services import audit_events as audit_event_service
from services import folders as folders_service
from services.folder_storage_policy import effective_cooldown_days, effective_min_tier
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
    cooldown_days: int | None = None
    min_tier: int | None = None
    effective_min_tier: int | None = None
    effective_cooldown_days: int | None = None

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
            cooldown_days=result.folder.cooldown_days,
            min_tier=result.folder.min_tier,
            effective_min_tier=effective_min_tier(db, result.folder),
            effective_cooldown_days=effective_cooldown_days(db, result.folder),
        )


class FolderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)


class FolderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    min_tier: int | None = None
    cooldown_days: int | None = Field(default=None, ge=1, le=36_500)

    @field_validator("min_tier")
    @classmethod
    def validate_min_tier_opt(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not 1 <= v <= 4:
            raise ValueError("min_tier must be between 1 and 4")
        return v


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
    cooldown_days: int | None = None
    min_tier: int | None = None
    effective_min_tier: int | None = None
    effective_cooldown_days: int | None = None
    children: list["FolderTreeRead"]


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
            _folder_to_tree_read(db, child, include_storage_policy=include_storage_policy)
            for child in folder.children
        ],
        cooldown_days=folder.cooldown_days if include_storage_policy else None,
        min_tier=folder.min_tier if include_storage_policy else None,
        effective_min_tier=effective_min_tier(db, folder)
        if include_storage_policy
        else None,
        effective_cooldown_days=effective_cooldown_days(db, folder)
        if include_storage_policy
        else None,
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
    New folders default to inheriting parent storage policy (no local overrides).
    Caller needs WRITE on the parent.
    """
    result = folders_service.create_folder(
        db,
        current_user,
        parent_id=payload.parent_id,
        name=payload.name,
        event_context=audit_event_service.context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
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
    PATCH /folders/{id} -> rename, move, and/or (admins) storage policy.
    Body: { name?, parent_id?, min_tier?, cooldown_days? }
    `min_tier` / `cooldown_days` are admin-only. Set to null to inherit from a
    parent (root must keep an explicit ``min_tier``).
    Caller needs WRITE on the folder, plus WRITE on the new parent when moving.
    Cycles (moving a folder into a descendant) are rejected.
    """
    result = folders_service.update_folder(
        db,
        current_user,
        folder_id=folder_id,
        name=payload.name,
        parent_id=payload.parent_id,
        min_tier=payload.min_tier,
        cooldown_days=payload.cooldown_days,
        set_min_tier="min_tier" in payload.model_fields_set,
        set_cooldown_days="cooldown_days" in payload.model_fields_set,
        event_context=audit_event_service.context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
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
        event_context=audit_event_service.context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
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
        event_context=audit_event_service.context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
        ),
    )
    return FolderRead.from_result(db, result, user=current_user)
