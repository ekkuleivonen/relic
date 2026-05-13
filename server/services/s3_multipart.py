import hashlib
import tempfile
import uuid
from dataclasses import dataclass
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

import settings as S
from managers.exceptions import BadRequestError, ResourceNotFound
from models import MultipartUpload, MultipartUploadPart, User
from schema_plan import BucketTier, Permission
from services import folder_access as folder_access_service
from services import objects as object_service
from services.event_context import EventContext
from services.folder_storage_policy import effective_min_tier
from services.placement import choose_bucket
from utils.logging import get_logger

log = get_logger(__name__)

MIN_PART_NUMBER = 1
MAX_PART_NUMBER = 10_000


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


def create_multipart_upload(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    ingest_meta: dict,
    current_user: User,
    event_context: EventContext | None = None,
) -> MultipartUpload:
    folder, file_name = object_service.resolve_object_path(
        db,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
        event_context=event_context,
    )
    folder_access_service.require_folder_permission_strict(
        db,
        current_user,
        folder.id,
        Permission.WRITE,
    )
    storage_bucket = choose_bucket(
        db,
        tier=BucketTier(effective_min_tier(db, folder)),
        size_bytes=0,
    )
    upload = MultipartUpload(
        bucket_name=bucket_name,
        object_key=object_service.normalize_key(key),
        folder_id=folder.id,
        file_name=file_name,
        uploaded_by=current_user.id,
        storage_bucket_id=storage_bucket.id,
        meta=ingest_meta,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return upload


def upload_part(
    db: Session,
    *,
    upload_id: uuid.UUID,
    bucket_name: str,
    key: str,
    part_number: int,
    body: BinaryIO,
    content_hash: bytes,
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
    )
    storage_bucket = upload.storage_bucket
    bucket_key = build_part_bucket_key(upload.id, part_number)
    etag = content_hash.hex()

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

    object_service.upload_blob(
        bucket=storage_bucket,
        bucket_key=bucket_key,
        body=body,
    )
    db.commit()
    return UploadedPart(part_number=part_number, etag=etag)


def complete_multipart_upload(
    db: Session,
    *,
    upload_id: uuid.UUID,
    bucket_name: str,
    key: str,
    requested_parts: list[CompleteMultipartPart],
    current_user: User,
    event_context: EventContext | None = None,
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
        boto_response = object_service.fetch_blob_bytes(
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

    put_result = object_service.put_object(
        db,
        bucket_name=upload.bucket_name,
        key=upload.object_key,
        body=assembled,
        content_hash=digest.digest(),
        size_bytes=total_size,
        ingest_meta=upload.meta,
        current_user=current_user,
        allow_overwrite=True,
        event_context=event_context,
    )

    for part in upload.parts:
        try:
            delete_part_bytes(upload, part)
        except BadRequestError as exc:
            log.warning(
                "multipart_temp_part_delete_failed",
                upload_id=str(upload.id),
                part_number=part.part_number,
                error=str(exc),
            )
    db.delete(upload)
    db.commit()
    return CompleteMultipartResult(
        bucket=bucket_name,
        key=key,
        etag=put_result.etag,
    )


def abort_multipart_upload(
    db: Session,
    *,
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
            delete_part_bytes(upload, part)
        except BadRequestError as exc:
            log.warning(
                "multipart_abort_part_delete_failed",
                upload_id=str(upload.id),
                part_number=part.part_number,
                error=str(exc),
            )
    db.delete(upload)
    db.commit()


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
    if upload.bucket_name != bucket_name or upload.object_key != object_service.normalize_key(key):
        raise ResourceNotFound("Multipart upload not found")
    folder_access_service.require_folder_permission_strict(
        db,
        current_user,
        upload.folder_id,
        Permission.WRITE,
    )
    return upload


def validate_part_number(part_number: int) -> None:
    if part_number < MIN_PART_NUMBER or part_number > MAX_PART_NUMBER:
        raise BadRequestError("partNumber must be between 1 and 10000")


def build_part_bucket_key(upload_id: uuid.UUID, part_number: int) -> str:
    return f"__relic_multipart_uploads/{upload_id}/{part_number}"


def delete_part_bytes(upload: MultipartUpload, part: MultipartUploadPart) -> None:
    object_service.delete_blob_bytes(
        bucket=upload.storage_bucket,
        bucket_key=part.bucket_key,
    )


def normalize_etag(value: str) -> str:
    return value.strip().strip('"')
