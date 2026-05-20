"""Session-level PutObject — internal gateway primitive.

HTTP routes and workers should call ``object_mutations.put_object(uow, ...)``
instead so list/folder caches are invalidated. Tests may call this directly
when exercising blob placement and dedup without cache side effects.
"""
from typing import BinaryIO

from enums import Permission
from domain.files.meta import normalize_ingest_meta
from infra.db.models import Blob, File, User
from ports.storage_registry import StorageRegistry
from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.db.stores import folder_access
from infra.db.stores.placement import choose_storage_backend, effective_preferred_storage_backend_id
from infra.gateway.object_blobs import create_blob, prepare_body
from infra.gateway.object_paths import resolve_object_path
from infra.gateway.object_types import PutObjectResult
from domain.exceptions import ConflictError
from domain.exceptions import BadRequestError
from ports.storage_policy import enforce_max_object_bytes, enforce_single_put_size
def put_object(
    db: Session,
    *,
    storage: StorageRegistry,
    bucket_name: str,
    key: str,
    body: bytes | BinaryIO,
    ingest_meta: dict,
    current_user: User,
    content_hash: bytes | None = None,
    size_bytes: int | None = None,
    allow_overwrite: bool = True,
) -> PutObjectResult:
    folder, file_name = resolve_object_path(
        db,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
    )
    folder_access.require_folder_permission_strict(
        db,
        current_user,
        folder.id,
        Permission.WRITE,
    )
    existing_file = db.scalar(
        select(File).where(File.folder_id == folder.id, File.name == file_name)
    )
    if existing_file is not None and not allow_overwrite:
        raise ConflictError("File already exists")
    previous_blob_id = existing_file.blob_id if existing_file is not None else None

    body_file, digest, object_size = prepare_body(
        body=body,
        content_hash=content_hash,
        size_bytes=size_bytes,
    )
    enforce_max_object_bytes(size_bytes=object_size)
    digest_hex = digest.hex()
    blob = db.scalar(select(Blob).where(Blob.content_hash == digest, Blob.refcount > 0))

    if blob:
        if existing_file is None or existing_file.blob_id != blob.id:
            blob.refcount += 1
    else:
        bucket = choose_storage_backend(
            db,
            size_bytes=object_size,
            preferred_storage_backend_id=effective_preferred_storage_backend_id(db, folder),
        )
        enforce_single_put_size(
            caps=storage.for_storage_backend(bucket).capabilities,
            size_bytes=object_size,
        )
        created_blob = create_blob(
            db,
            storage=storage,
            bucket=bucket,
            digest=digest,
            body=body_file,
            size_bytes=object_size,
            filename=file_name,
        )
        blob = created_blob.blob

    if existing_file is None:
        file = File(
            folder_id=folder.id,
            blob_id=blob.id,
            actor_id=current_user.id,
            name=file_name,
            meta=normalize_ingest_meta(ingest_meta),
        )
        db.add(file)
    else:
        file = existing_file
        old_blob = db.get(Blob, previous_blob_id)
        file.blob_id = blob.id
        file.actor_id = current_user.id
        file.meta = normalize_ingest_meta(ingest_meta)
        if old_blob is not None and old_blob.id != blob.id:
            old_blob.refcount -= 1
            if old_blob.refcount < 0:
                old_blob.refcount = 0
    db.flush()
    return PutObjectResult(file=file, blob=blob, etag=digest_hex)
