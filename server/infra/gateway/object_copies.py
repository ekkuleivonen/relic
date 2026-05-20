"""Session-level CopyObject — internal gateway primitive. Prefer ``object_mutations.copy_object``."""
from constants import (
    S3_METADATA_DIRECTIVE_COPY,
    S3_METADATA_DIRECTIVE_REPLACE,
)
from enums import Permission
from domain.exceptions import BadRequestError, ResourceNotFound
from domain.files.meta import normalize_ingest_meta
from infra.db.models import Blob, File, User
from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.db.stores import folder_access
from infra.gateway.object_blobs import ensure_file_name_available
from infra.gateway.object_paths import (
    require_existing_object_path,
    resolve_object_path,
)
from infra.gateway.object_types import CopyObjectResult


def copy_object(
    db: Session,
    *,
    source_bucket: str,
    source_key: str,
    dest_bucket: str,
    dest_key: str,
    ingest_meta: dict,
    metadata_directive: str = S3_METADATA_DIRECTIVE_COPY,
    current_user: User,
) -> CopyObjectResult:
    if metadata_directive not in (
        S3_METADATA_DIRECTIVE_COPY,
        S3_METADATA_DIRECTIVE_REPLACE,
    ):
        raise BadRequestError("x-amz-metadata-directive must be COPY or REPLACE")

    source_folder, source_file_name = require_existing_object_path(
        db, bucket_name=source_bucket, key=source_key
    )
    source_file = db.scalar(
        select(File).where(
            File.folder_id == source_folder.id, File.name == source_file_name
        )
    )
    if source_file is None:
        raise ResourceNotFound("Source object not found")

    folder_access.require_folder_permission_strict(
        db, current_user, source_folder.id, Permission.READ
    )

    dest_folder, dest_file_name = resolve_object_path(
        db,
        bucket_name=dest_bucket,
        key=dest_key,
        current_user=current_user,
    )

    if (
        source_folder.id == dest_folder.id
        and source_file_name == dest_file_name
        and metadata_directive == S3_METADATA_DIRECTIVE_COPY
    ):
        raise BadRequestError(
            "Source and destination must differ when metadata-directive is COPY"
        )

    folder_access.require_folder_permission_strict(
        db, current_user, dest_folder.id, Permission.WRITE
    )

    ensure_file_name_available(db, dest_folder.id, dest_file_name)

    blob = db.get(Blob, source_file.blob_id)
    if blob is None:
        raise ResourceNotFound("Source blob not found")

    copied_meta = (
        dict(source_file.meta or {})
        if metadata_directive == S3_METADATA_DIRECTIVE_COPY
        else normalize_ingest_meta(ingest_meta)
    )

    new_file = File(
        folder_id=dest_folder.id,
        blob_id=blob.id,
        actor_id=current_user.id,
        name=dest_file_name,
        meta=copied_meta,
    )
    db.add(new_file)
    blob.refcount += 1
    db.flush()

    etag = blob.content_hash.hex()
    return CopyObjectResult(
        file=new_file,
        blob=blob,
        etag=etag,
        source_file_id=source_file.id,
    )
