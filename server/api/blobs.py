from fastapi import APIRouter, Request, Response

router = APIRouter()

"""
Blob management - the physical layer.

Most blob operations are internal (refcount maintenance, GC, tiering).
The endpoints here are for admin/debug access and for the rare case where
a tool needs to address a blob directly by content hash rather than via
a File reference.
"""


@router.get("/")
async def list_blobs(request: Request) -> Response:
    """
    GET /blobs -> list blobs.
    Query params:
      ?storage_id=<uuid>      blobs on a specific storage
      ?refcount=0             blobs scheduled for GC (refcount < 1)
      ?content_hash=<hex>     lookup by hash
      ?accessed_before=<ts>   tiering candidate query
      ?limit=50&cursor=<id>   pagination
    Admin-only by default; non-admins only see blobs referenced by files
    they can read.
    """
    raise NotImplementedError


@router.get("/{blob_id}")
async def get_blob(blob_id: str, request: Request) -> Response:
    """
    GET /blobs/{id} -> single blob with current storage, refcount, hash.
    Includes referenced_by: a list of (folder_id, file_id, file_name) for
    every File pointing at this Blob. Useful for "where does this content
    live?" debugging.
    """
    raise NotImplementedError


@router.post("/{blob_id}/migrate")
async def migrate_blob(blob_id: str, request: Request) -> Response:
    """
    POST /blobs/{id}/migrate -> move bytes to a different Storage.
    Body: { destination_storage_id }
    Streams bytes between storages, updates Blob.storage_id atomically on
    success, deletes from source after verification.
    Used by tiering jobs and manual ops; rarely called by humans.
    Admin-only.
    """
    raise NotImplementedError


@router.delete("/{blob_id}")
async def delete_blob(blob_id: str, request: Request) -> Response:
    """
    DELETE /blobs/{id} -> force-delete a blob.
    Refuses if refcount > 0 unless ?force=true (which also deletes all
    referencing files - dangerous).
    Normally GC handles this automatically when refcount hits 0; this
    endpoint is for stuck cleanup scenarios.
    Admin-only.
    """
    raise NotImplementedError


@router.post("/gc")
async def trigger_gc(request: Request) -> Response:
    """
    POST /blobs/gc -> run garbage collection over blobs with refcount < 1.
    Returns: { scanned, deleted, freed_bytes }
    Normally a cron job does this; this is the manual trigger.
    Admin-only.
    """
    raise NotImplementedError
