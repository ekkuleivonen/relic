"""Session-level DeleteObject — internal gateway primitive. Prefer ``object_mutations.delete_object``."""
from enums import Permission
from infra.db.models import Blob, File, User
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.control_plane import folder_access
from application.gateway.object_paths import resolve_existing_object_path
from application.gateway.object_types import DeleteObjectResult
from infra.cache.hotpath import clear_list_objects_response_cache


def delete_object(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
    commit: bool = False,
) -> DeleteObjectResult:
    folder, file_name = resolve_existing_object_path(
        db, bucket_name=bucket_name, key=key
    )
    if folder is None:
        return DeleteObjectResult(existed=False)

    if current_user is not None:
        folder_access.require_folder_permission_strict(
            db,
            current_user,
            folder.id,
            Permission.DELETE,
        )

    file = db.scalar(
        select(File).where(File.folder_id == folder.id, File.name == file_name)
    )
    if file is None:
        return DeleteObjectResult(existed=False)

    blob = db.get(Blob, file.blob_id)
    db.delete(file)
    db.flush()

    if blob is not None:
        blob.refcount -= 1
        if blob.refcount < 0:
            blob.refcount = 0

    if commit:
        db.commit()
        clear_list_objects_response_cache()
    return DeleteObjectResult(existed=True)
