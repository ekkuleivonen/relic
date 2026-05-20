import hashlib
import tempfile
import uuid
from dataclasses import dataclass
from typing import BinaryIO

import settings as S
from constants import S3_MULTIPART_MAX_PART_NUMBER, S3_MULTIPART_MIN_PART_NUMBER
from enums import Permission
from domain.exceptions import BadRequestError, ResourceNotFound
from infra.db.models import MultipartUpload, MultipartUploadPart, User
from ports.repositories.multipart import MultipartStore
from ports.storage_registry import StorageRegistry
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from utils.logging import get_logger

from application.control_plane import folder_access
from application.gateway import blob_storage
from application.gateway import object_paths
from application.gateway import object_writes
from application.control_plane.placement import choose_bucket, effective_preferred_bucket_id

log = get_logger(__name__)


@dataclass(frozen=True)
class UploadedPart:
    part_number: int
    etag: str


@dataclass(frozen=True)
class CompleteMultipartPart:
    part_number: int
    etag: str | None


@dataclass(frozen=True)
class CompleteMultipartResult:
    bucket: str
    key: str
    etag: str


@dataclass(frozen=True)
class MultipartUploadListPage:
    uploads: list[MultipartUpload]


@dataclass(frozen=True)
class MultipartPartListPage:
    upload: MultipartUpload
    parts: list[MultipartUploadPart]


def create_multipart_upload(
    db: Session,
    *,
    multipart_store: MultipartStore,
    bucket_name: str,
    key: str,
    ingest_meta: dict,
    current_user: User,
    commit: bool = False,
) -> MultipartUpload:
    folder, _file_name = object_paths.resolve_object_path(
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
    storage_bucket = choose_bucket(
        db,
        size_bytes=0,
        preferred_bucket_id=effective_preferred_bucket_id(db, folder),
    )
    upload = MultipartUpload(
        bucket_name=bucket_name,
        object_key=object_paths.normalize_key(key),
        folder_id=folder.id,
        actor_id=current_user.id,
        storage_bucket_id=storage_bucket.id,
        meta=ingest_meta,
    )
    if commit:
        created = multipart_store.create(upload)
        db.commit()
        return created
    return multipart_store.create(upload)


def upload_part(
    db: Session,
    *,
    storage: StorageRegistry,
    upload_id: uuid.UUID,
    bucket_name: str,
    key: str,
    part_number: int,
    body: BinaryIO,
    content_hash: bytes,
    content_md5: bytes,
    size_bytes: int,
    current_user: User,
    commit: bool = False,
) -> UploadedPart:
    validate_part_number(part_number)
    upload = require_upload(
        db,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
    )
    storage_bucket = upload.storage_bucket
    bucket_key = build_part_bucket_key(upload.id, part_number)
    etag = content_md5.hex()

    existing = db.scalar(
        select(MultipartUploadPart).where(
            MultipartUploadPart.upload_id == upload.id,
            MultipartUploadPart.part_number == part_number,
        )
    )
    if existing is not None:
        existing.bucket_key = bucket_key
        existing.content_hash = content_hash
        existing.size_bytes = size_bytes
        existing.etag = etag
        part = existing
    else:
        part = MultipartUploadPart(
            upload_id=upload.id,
            part_number=part_number,
            bucket_key=bucket_key,
            content_hash=content_hash,
            size_bytes=size_bytes,
            etag=etag,
        )
        db.add(part)

    blob_storage.upload_blob(
        storage=storage,
        bucket=storage_bucket,
        bucket_key=bucket_key,
        body=body,
    )
    if commit:
        db.commit()
    return UploadedPart(part_number=part_number, etag=etag)


def complete_multipart_upload(
    db: Session,
    *,
    storage: StorageRegistry,
    upload_id: uuid.UUID,
    bucket_name: str,
    key: str,
    requested_parts: list[CompleteMultipartPart],
    current_user: User,
    commit: bool = False,
) -> CompleteMultipartResult:
    upload = require_upload(
        db,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
        with_parts=True,
    )
    if not requested_parts:
        raise BadRequestError("CompleteMultipartUpload requires at least one part")

    by_part_number = {part.part_number: part for part in upload.parts}
    assembled = tempfile.SpooledTemporaryFile(max_size=S.UPLOAD_SPOOL_MAX_MEMORY_BYTES)
    digest = hashlib.sha256()
    total_size = 0
    ordered_parts: list[MultipartUploadPart] = []

    for requested in requested_parts:
        validate_part_number(requested.part_number)
        part = by_part_number.get(requested.part_number)
        if part is None:
            raise BadRequestError(f"Part {requested.part_number} has not been uploaded")
        if requested.etag is not None and normalize_etag(requested.etag) != part.etag:
            raise BadRequestError(f"ETag mismatch for part {requested.part_number}")
        ordered_parts.append(part)

    for part in ordered_parts:
        boto_response = blob_storage.fetch_blob_bytes(
            storage=storage,
            bucket=upload.storage_bucket,
            bucket_key=part.bucket_key,
        )
        stream = boto_response["Body"]
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            assembled.write(chunk)
            total_size += len(chunk)
    assembled.seek(0)
    completed_etag = build_complete_multipart_etag(ordered_parts)

    put_result = object_writes.put_object(
        db,
        storage=storage,
        bucket_name=upload.bucket_name,
        key=upload.object_key,
        body=assembled,
        content_hash=digest.digest(),
        size_bytes=total_size,
        ingest_meta=upload.meta,
        current_user=current_user,
        allow_overwrite=True,
        commit=False,
    )

    for part in upload.parts:
        try:
            delete_part_bytes(upload, part, storage=storage)
        except BadRequestError as exc:
            log.warning(
                "multipart_temp_part_delete_failed",
                upload_id=str(upload.id),
                part_number=part.part_number,
                error=str(exc),
            )
    db.delete(upload)
    if commit:
        db.commit()
    return CompleteMultipartResult(
        bucket=bucket_name,
        key=key,
        etag=completed_etag or put_result.etag,
    )


def abort_multipart_upload(
    db: Session,
    *,
    storage: StorageRegistry,
    upload_id: uuid.UUID,
    bucket_name: str,
    key: str,
    current_user: User,
    commit: bool = False,
) -> None:
    upload = require_upload(
        db,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
        with_parts=True,
    )
    for part in upload.parts:
        try:
            delete_part_bytes(upload, part, storage=storage)
        except BadRequestError as exc:
            log.warning(
                "multipart_abort_part_delete_failed",
                upload_id=str(upload.id),
                part_number=part.part_number,
                error=str(exc),
            )
    db.delete(upload)
    if commit:
        db.commit()


def list_multipart_uploads(
    db: Session,
    *,
    bucket_name: str,
    current_user: User,
) -> MultipartUploadListPage:
    uploads = list(
        db.scalars(
            select(MultipartUpload)
            .where(MultipartUpload.bucket_name == bucket_name)
            .order_by(MultipartUpload.created_at.asc(), MultipartUpload.id.asc())
        )
    )
    visible = [
        upload
        for upload in uploads
        if folder_access.get_effective_permissions(
            db, current_user, upload.folder_id
        )
        & int(Permission.WRITE)
    ]
    return MultipartUploadListPage(uploads=visible)


def list_multipart_parts(
    db: Session,
    *,
    upload_id: uuid.UUID,
    bucket_name: str,
    key: str,
    current_user: User,
) -> MultipartPartListPage:
    upload = require_upload(
        db,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
        with_parts=True,
    )
    return MultipartPartListPage(upload=upload, parts=list(upload.parts))


def abort_incomplete_uploads_older_than(
    db: Session, cutoff, *, storage: StorageRegistry, commit: bool = False
) -> int:
    uploads = list(
        db.scalars(
            select(MultipartUpload)
            .where(MultipartUpload.created_at < cutoff)
            .options(
                selectinload(MultipartUpload.parts),
                selectinload(MultipartUpload.storage_bucket),
            )
        )
    )
    for upload in uploads:
        for part in upload.parts:
            try:
                delete_part_bytes(upload, part, storage=storage)
            except BadRequestError as exc:
                log.warning(
                    "multipart_cleanup_part_delete_failed",
                    upload_id=str(upload.id),
                    part_number=part.part_number,
                    error=str(exc),
                )
        db.delete(upload)
    if commit:
        db.commit()
    return len(uploads)


def require_upload(
    db: Session,
    *,
    upload_id: uuid.UUID,
    bucket_name: str,
    key: str,
    current_user: User,
    with_parts: bool = False,
) -> MultipartUpload:
    stmt = select(MultipartUpload).where(MultipartUpload.id == upload_id)
    if with_parts:
        stmt = stmt.options(
            selectinload(MultipartUpload.parts),
            selectinload(MultipartUpload.storage_bucket),
        )
    upload = db.scalar(stmt)
    if upload is None:
        raise ResourceNotFound("Multipart upload not found")
    if (
        upload.bucket_name != bucket_name
        or upload.object_key != object_paths.normalize_key(key)
    ):
        raise ResourceNotFound("Multipart upload not found")
    folder_access.require_folder_permission_strict(
        db,
        current_user,
        upload.folder_id,
        Permission.WRITE,
    )
    return upload


def validate_part_number(part_number: int) -> None:
    if (
        part_number < S3_MULTIPART_MIN_PART_NUMBER
        or part_number > S3_MULTIPART_MAX_PART_NUMBER
    ):
        raise BadRequestError("partNumber must be between 1 and 10000")


def build_part_bucket_key(upload_id: uuid.UUID, part_number: int) -> str:
    return f"__relic_multipart_uploads/{upload_id}/{part_number}"


def build_complete_multipart_etag(parts: list[MultipartUploadPart]) -> str | None:
    if not parts:
        return None
    try:
        digest = hashlib.md5(usedforsecurity=False)
    except TypeError:
        digest = hashlib.md5()
    for part in parts:
        digest.update(bytes.fromhex(part.etag))
    return f"{digest.hexdigest()}-{len(parts)}"


def delete_part_bytes(
    upload: MultipartUpload, part: MultipartUploadPart, *, storage: StorageRegistry
) -> None:
    blob_storage.delete_blob_bytes(
        storage=storage,
        bucket=upload.storage_bucket,
        bucket_key=part.bucket_key,
    )


def normalize_etag(value: str) -> str:
    return value.strip().strip('"')
