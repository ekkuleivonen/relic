"""Session-level GetObject/HeadObject — internal gateway primitive."""
from enums import Permission
from domain.exceptions import ResourceNotFound
from infra.db.models import Blob, StorageBackend, File, User
from ports.storage_registry import StorageRegistry
from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.db.stores import folder_access
from infra.gateway import blob_storage
from infra.gateway.object_paths import require_existing_object_path
from infra.gateway.object_types import GetObjectBytesResult, GetObjectResult


def get_object(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
) -> GetObjectResult:
    folder, file_name = require_existing_object_path(
        db, bucket_name=bucket_name, key=key
    )
    file = db.scalar(
        select(File).where(File.folder_id == folder.id, File.name == file_name)
    )
    if file is None:
        raise ResourceNotFound("Object not found")

    if current_user is not None:
        folder_access.require_folder_permission_strict(
            db, current_user, folder.id, Permission.READ
        )

    blob = db.get(Blob, file.blob_id)
    if blob is None:
        raise ResourceNotFound("Object bytes not found")

    bucket = db.get(StorageBackend, blob.storage_backend_id)
    if bucket is None:
        raise ResourceNotFound("Backing bucket not found")

    return GetObjectResult(file=file, blob=blob, bucket=bucket)


def head_object(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
) -> GetObjectResult:
    return get_object(db, bucket_name=bucket_name, key=key, current_user=current_user)


def get_object_bytes(
    db: Session,
    *,
    storage: StorageRegistry,
    bucket_name: str,
    key: str,
    range_header: str | None = None,
    current_user: User | None = None,
) -> GetObjectBytesResult:
    result = get_object(db, bucket_name=bucket_name, key=key, current_user=current_user)
    boto_response = blob_storage.fetch_blob_bytes(
        storage=storage,
        bucket=result.bucket,
        bucket_key=result.blob.bucket_key,
        range_header=range_header,
    )
    return GetObjectBytesResult(result=result, boto_response=boto_response)
