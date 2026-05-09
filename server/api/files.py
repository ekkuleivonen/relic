import datetime as dt
import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from database import DbSession
from services import filesystem as filesystem_service

router = APIRouter()

"""
File CRUD - the logical references inside folders.

Note: byte upload/download lives at the S3 gateway, not here. These routes
manage the metadata records and handle queries.
"""


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    folder_id: uuid.UUID
    blob_id: uuid.UUID
    name: str
    meta: dict
    created_at: dt.datetime
    updated_at: dt.datetime
    accessed_at: dt.datetime


@router.get("/")
async def list_files(
    request: Request,
    db: DbSession,
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
) -> list[FileRead]:
    """
    GET /files -> list files matching query.
    Query params:
      ?folder_id=<uuid>       limit to one folder
      ?recursive=true         include descendants of folder_id
      ?meta.<key>=<value>     filter by metadata field (uses GIN once added)
      ?name_prefix=<str>      filename starts-with filter
      ?limit=50&cursor=<id>   pagination
      ?order=created_at:desc  sort
    Returns files the caller has READ on (via folder ACL walk).
    """
    return filesystem_service.list_files(db, folder_id=folder_id, recursive=recursive)


@router.post("/")
async def create_file(request: Request) -> Response:
    """
    POST /files -> register a File pointing at an existing Blob.
    Body: { folder_id, name, blob_id, meta }
    Used for: registering pre-existing blobs (after direct PUT to a Bucket),
    bulk imports, or creating references during migrations.
    Schema validation runs against folder's schema.

    Most clients don't use this directly - they use the S3 PUT path. This
    endpoint is for cases where bytes are already in place and only metadata
    needs creating.
    """
    raise NotImplementedError


@router.get("/{file_id}")
async def get_file(file_id: str, request: Request) -> Response:
    """
    GET /files/{id} -> single file with meta, folder, blob reference.
    Includes derived blob fields (size, mime_type, content_hash) for
    convenience.
    """
    raise NotImplementedError


@router.patch("/{file_id}")
async def update_file(file_id: str, request: Request) -> Response:
    """
    PATCH /files/{id} -> update mutable fields.
    Body: { name?, meta? }
    meta updates merge with existing meta (use null values to delete keys).
    Re-validates against folder schema after merge.
    Caller needs WRITE or ENRICH permission.
    """
    raise NotImplementedError


@router.delete("/{file_id}")
async def delete_file(file_id: str, request: Request) -> Response:
    """
    DELETE /files/{id} -> remove file reference.
    Decrements Blob.refcount; GC if it hits 0.
    Caller needs DELETE permission.
    """
    raise NotImplementedError


@router.post("/{file_id}/copy")
async def copy_file(file_id: str, request: Request) -> Response:
    """
    POST /files/{id}/copy -> create a new File pointing at the same Blob.
    Body: { destination_folder_id, name? }
    Free metadata-only copy. Validates merged meta against destination
    folder's schema (may differ from source's).
    Increments Blob.refcount.
    """
    raise NotImplementedError


@router.post("/{file_id}/move")
async def move_file(file_id: str, request: Request) -> Response:
    """
    POST /files/{id}/move -> change folder_id and/or name.
    Body: { destination_folder_id?, name? }
    Re-validates meta against new folder's schema if folder changes.
    Atomic; refcount on Blob unchanged.
    """
    raise NotImplementedError


@router.get("/{file_id}/download")
async def download_file_url(file_id: str, request: Request) -> Response:
    """
    GET /files/{id}/download -> issue a pre-signed URL for direct GET from
    the S3 gateway.
    Convenience for UI that doesn't want to wire up SigV4 itself.
    Returns: { url, expires_at }
    """
    raise NotImplementedError
