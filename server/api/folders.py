import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from api.dependencies import CurrentUser
from database import DbSession
from services import filesystem as filesystem_service

router = APIRouter()

"""
Folder CRUD - the virtual filesystem.

Most user-facing operations: browsing, creating subfolders, editing schemas,
managing per-folder cooldown policies.
"""


@router.get("/")
async def list_folders(request: Request) -> Response:
    """
    GET /folders -> list folders the caller can see.
    Query params: ?parent_id=<uuid> to list children; omit for root + top-level.
    Returns flat list, not tree. UI assembles the tree from parent_ids.
    """
    raise NotImplementedError


@router.post("/")
async def create_folder(request: Request) -> Response:
    """
    POST /folders -> create a new folder.
    Body: { name, parent_id, schema?, cooldown_days?, min_tier? }
    Schema must be a valid JSON Schema and a superset of parent's schema.
    Caller needs ADMIN permission on parent.
    """
    raise NotImplementedError


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


@router.get("/{folder_id}")
async def get_folder(folder_id: str, request: Request) -> Response:
    """
    GET /folders/{id} -> single folder with schema, policy, parent.
    Includes derived fields: file_count, total_size, effective_permissions
    for the caller.
    """
    raise NotImplementedError


@router.patch("/{folder_id}")
async def update_folder(folder_id: str, request: Request) -> Response:
    """
    PATCH /folders/{id} -> update mutable fields.
    Body: { name?, schema?, cooldown_days?, min_tier? }
    Schema changes must remain a superset of parent's schema and a superset
    of any existing child folder schemas.
    Caller needs ADMIN permission.
    """
    raise NotImplementedError


@router.delete("/{folder_id}")
async def delete_folder(folder_id: str, request: Request) -> Response:
    """
    DELETE /folders/{id} -> delete folder.
    Refuses if folder has files or subfolders unless ?recursive=true.
    Recursive delete decrements refcounts on all referenced blobs;
    blobs hitting refcount 0 are GC'd.
    Cannot delete root.
    """
    raise NotImplementedError


@router.get("/{folder_id}/access")
async def list_folder_access(folder_id: str, request: Request) -> Response:
    """
    GET /folders/{id}/access -> ACL rows directly attached to this folder.
    Does not include inherited rules; use ?effective=true to compute the
    union up the tree per user.
    """
    raise NotImplementedError


@router.post("/{folder_id}/access")
async def grant_folder_access(folder_id: str, request: Request) -> Response:
    """
    POST /folders/{id}/access -> grant a user permissions on this folder.
    Body: { user_id, permissions }
    permissions is an integer bitfield (READ=1, WRITE=2, DELETE=4, ENRICH=8).
    Idempotent - existing rule for the same user is updated.
    Caller needs ADMIN permission.
    """
    raise NotImplementedError


@router.delete("/{folder_id}/access/{user_id}")
async def revoke_folder_access(
    folder_id: str, user_id: str, request: Request
) -> Response:
    """
    DELETE /folders/{id}/access/{user_id} -> revoke explicit grant.
    Inherited permissions from ancestor folders remain in effect.
    """
    raise NotImplementedError


@router.post("/{folder_id}/copy")
async def copy_folder(folder_id: str, request: Request) -> Response:
    """
    POST /folders/{id}/copy -> create a metadata-only copy of the folder
    and all its files at a new location.
    Body: { destination_parent_id, name, recursive?: bool }
    No bytes moved; refcounts on referenced blobs are incremented.
    This is the folder-as-versioning primitive surfaced as an explicit
    operation (CopyObject at S3 level handles single files).
    """
    raise NotImplementedError


@router.post("/{folder_id}/snapshot")
async def snapshot_folder(folder_id: str, request: Request) -> Response:
    """
    POST /folders/{id}/snapshot -> create a frozen snapshot folder.
    Body: { name?, parent_id? }   (defaults: timestamp name under /snapshots)
    Same as copy, but the result is marked read-only.
    """
    raise NotImplementedError
