import hashlib
import tempfile
import uuid
from dataclasses import dataclass
from typing import BinaryIO

import settings as S
from constants import FILE_INFO_PREFIX_BYTES
from constants import S3_MULTIPART_MAX_PART_NUMBER, S3_MULTIPART_MIN_PART_NUMBER
from enums import Permission
from domain.files.meta import normalize_ingest_meta
from domain.exceptions import BadRequestError, ResourceNotFound
from infra.db.models import Blob, File, MultipartUpload, MultipartUploadPart, User
from ports.repositories.multipart import MultipartStore
from ports.storage_registry import StorageRegistry
from ports.storage_policy import enforce_max_object_bytes, enforce_multipart
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from utils.logging import get_logger

from infra.db.stores import folder_access
from infra.gateway import blob_storage
from infra.gateway import object_blobs
from infra.gateway import object_paths
from infra.gateway import object_writes
from infra.gateway.object_types import PutObjectResult
from infra.db.stores.placement import choose_storage_backend, effective_preferred_storage_backend_id

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
    file: File | None = None
    blob: Blob | None = None
    created: bool = False
    previous_blob_id: uuid.UUID | None = None


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
    storage: StorageRegistry,
    multipart_store: MultipartStore,
    bucket_name: str,
    key: str,
    ingest_meta: dict,
    current_user: User,
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
    storage_bucket = choose_storage_backend(
        db,
        size_bytes=0,
        preferred_storage_backend_id=effective_preferred_storage_backend_id(db, folder),
    )
    enforce_multipart(caps=storage.for_storage_backend(storage_bucket).capabilities)
    upload = MultipartUpload(
        bucket_name=bucket_name,
        object_key=object_paths.normalize_key(key),
        folder_id=folder.id,
        actor_id=current_user.id,
        storage_backend_id=storage_bucket.id,
        meta=ingest_meta,
    )
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
) -> UploadedPart:
    validate_part_number(part_number)
    upload = require_upload(
        db,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
        with_parts=True,
    )
    projected_total = size_bytes + sum(
        part.size_bytes
        for part in upload.parts
        if part.part_number != part_number
    )
    enforce_max_object_bytes(size_bytes=projected_total)
    storage_bucket = upload.storage_backend
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

    ordered_parts = _validate_complete_parts(upload, requested_parts)
    completed_etag = build_complete_multipart_etag(ordered_parts)
    adapter = storage.for_storage_backend(upload.storage_backend)

    if adapter.capabilities.server_side_copy:
        digest, total_size, prefix = _hash_parts(
            storage=storage,
            upload=upload,
            ordered_parts=ordered_parts,
        )
        put_result = _put_composed_object(
            db,
            storage=storage,
            upload=upload,
            ordered_parts=ordered_parts,
            digest=digest,
            size_bytes=total_size,
            prefix=prefix,
            current_user=current_user,
        )
        put_etag = put_result.etag
    else:
        assembled, digest, total_size = _assemble_parts(
            storage=storage,
            upload=upload,
            ordered_parts=ordered_parts,
        )
        put_result = object_writes.put_object(
            db,
            storage=storage,
            bucket_name=upload.bucket_name,
            key=upload.object_key,
            body=assembled,
            content_hash=digest,
            size_bytes=total_size,
            ingest_meta=upload.meta,
            current_user=current_user,
            allow_overwrite=True,
        )
        put_etag = put_result.etag

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
    return CompleteMultipartResult(
        bucket=bucket_name,
        key=key,
        etag=completed_etag or put_etag,
        file=put_result.file,
        blob=put_result.blob,
        created=put_result.created,
        previous_blob_id=put_result.previous_blob_id,
    )


def _validate_complete_parts(
    upload: MultipartUpload,
    requested_parts: list[CompleteMultipartPart],
) -> list[MultipartUploadPart]:
    by_part_number = {part.part_number: part for part in upload.parts}
    ordered_parts: list[MultipartUploadPart] = []
    for requested in requested_parts:
        validate_part_number(requested.part_number)
        part = by_part_number.get(requested.part_number)
        if part is None:
            raise BadRequestError(f"Part {requested.part_number} has not been uploaded")
        if requested.etag is not None and normalize_etag(requested.etag) != part.etag:
            raise BadRequestError(f"ETag mismatch for part {requested.part_number}")
        ordered_parts.append(part)
    return ordered_parts


def _hash_parts(
    *,
    storage: StorageRegistry,
    upload: MultipartUpload,
    ordered_parts: list[MultipartUploadPart],
) -> tuple[bytes, int, bytes]:
    digest = hashlib.sha256()
    total_size = 0
    prefix = bytearray()
    for part in ordered_parts:
        boto_response = blob_storage.fetch_blob_bytes(
            storage=storage,
            bucket=upload.storage_backend,
            bucket_key=part.bucket_key,
        )
        stream = boto_response["Body"]
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                enforce_max_object_bytes(size_bytes=total_size)
                digest.update(chunk)
                if len(prefix) < FILE_INFO_PREFIX_BYTES:
                    remaining = FILE_INFO_PREFIX_BYTES - len(prefix)
                    prefix.extend(chunk[:remaining])
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
    return digest.digest(), total_size, bytes(prefix)


def _assemble_parts(
    *,
    storage: StorageRegistry,
    upload: MultipartUpload,
    ordered_parts: list[MultipartUploadPart],
):
    assembled = tempfile.SpooledTemporaryFile(max_size=S.UPLOAD_SPOOL_MAX_MEMORY_BYTES)
    digest = hashlib.sha256()
    total_size = 0
    for part in ordered_parts:
        boto_response = blob_storage.fetch_blob_bytes(
            storage=storage,
            bucket=upload.storage_backend,
            bucket_key=part.bucket_key,
        )
        stream = boto_response["Body"]
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                enforce_max_object_bytes(size_bytes=total_size)
                digest.update(chunk)
                assembled.write(chunk)
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
    assembled.seek(0)
    return assembled, digest.digest(), total_size


def _put_composed_object(
    db: Session,
    *,
    storage: StorageRegistry,
    upload: MultipartUpload,
    ordered_parts: list[MultipartUploadPart],
    digest: bytes,
    size_bytes: int,
    prefix: bytes,
    current_user: User,
) -> PutObjectResult:
    folder, file_name = object_paths.resolve_object_path(
        db,
        bucket_name=upload.bucket_name,
        key=upload.object_key,
        current_user=current_user,
    )
    existing_file = db.scalar(
        select(File).where(File.folder_id == folder.id, File.name == file_name)
    )
    previous_blob_id = existing_file.blob_id if existing_file is not None else None
    blob = db.scalar(select(Blob).where(Blob.content_hash == digest, Blob.refcount > 0))
    if blob:
        if existing_file is None or existing_file.blob_id != blob.id:
            blob.refcount += 1
        etag = digest.hex()
    else:
        created_blob = object_blobs.create_composed_blob(
            db,
            storage=storage,
            bucket=upload.storage_backend,
            digest=digest,
            size_bytes=size_bytes,
            filename=file_name,
            source_keys=[part.bucket_key for part in ordered_parts],
            prefix=prefix,
        )
        blob = created_blob.blob
        etag = digest.hex()

    if existing_file is None:
        file = File(
            folder_id=folder.id,
            blob_id=blob.id,
            actor_id=current_user.id,
            name=file_name,
            meta=normalize_ingest_meta(upload.meta),
        )
        db.add(file)
    else:
        file = existing_file
        old_blob = db.get(Blob, previous_blob_id)
        existing_file.blob_id = blob.id
        existing_file.actor_id = current_user.id
        existing_file.meta = normalize_ingest_meta(upload.meta)
        if old_blob is not None and old_blob.id != blob.id:
            old_blob.refcount -= 1
            if old_blob.refcount < 0:
                old_blob.refcount = 0
    db.flush()
    return PutObjectResult(
        file=file,
        blob=blob,
        etag=etag,
        created=existing_file is None,
        previous_blob_id=previous_blob_id,
    )


def abort_multipart_upload(
    db: Session,
    *,
    storage: StorageRegistry,
    upload_id: uuid.UUID,
    bucket_name: str,
    key: str,
    current_user: User,
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
    db: Session, cutoff, *, storage: StorageRegistry
) -> int:
    uploads = list(
        db.scalars(
            select(MultipartUpload)
            .where(MultipartUpload.created_at < cutoff)
            .options(
                selectinload(MultipartUpload.parts),
                selectinload(MultipartUpload.storage_backend),
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
            selectinload(MultipartUpload.storage_backend),
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
        bucket=upload.storage_backend,
        bucket_key=part.bucket_key,
    )


def normalize_etag(value: str) -> str:
    return value.strip().strip('"')
