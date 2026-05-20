"""Public gateway mutation API — call from routes and workers via UnitOfWork.

Wraps session-level verb modules (``object_writes``, ``object_deletes``, …),
commits through the UoW session, and invalidates list/folder hot-path caches.
Do not call ``object_writes.put_object`` directly from HTTP handlers; use
``put_object(uow, ...)`` here so cache coherence is preserved.
"""

from typing import BinaryIO

from infra.gateway import object_multipart
from infra.gateway import object_writes
from application.gateway import delete_object as delete_object_use_case
from infra.gateway import object_copies
from infra.gateway.object_multipart import (
    CompleteMultipartPart,
    CompleteMultipartResult,
    MultipartPartListPage,
    MultipartUploadListPage,
    UploadedPart,
)
from infra.gateway.object_types import CopyObjectResult, DeleteObjectResult, PutObjectResult
from application.uow import UnitOfWork
from infra.db.models import MultipartUpload, User


def put_object(
    uow: UnitOfWork,
    *,
    bucket_name: str,
    key: str,
    body: bytes | BinaryIO,
    ingest_meta: dict,
    current_user: User,
    content_hash: bytes | None = None,
    size_bytes: int | None = None,
    allow_overwrite: bool = True,
) -> PutObjectResult:
    result = object_writes.put_object(
        uow.session,
        storage=uow.storage,
        bucket_name=bucket_name,
        key=key,
        body=body,
        ingest_meta=ingest_meta,
        current_user=current_user,
        content_hash=content_hash,
        size_bytes=size_bytes,
        allow_overwrite=allow_overwrite,
    )
    uow.cache.invalidate_list_objects()
    uow.cache.invalidate_folder_hotpath(uow.session)
    return result


def delete_object(
    uow: UnitOfWork,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
) -> DeleteObjectResult:
    return delete_object_use_case.delete_object(
        uow,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
    )


def copy_object(
    uow: UnitOfWork,
    *,
    source_bucket: str,
    source_key: str,
    dest_bucket: str,
    dest_key: str,
    ingest_meta: dict,
    metadata_directive: str,
    current_user: User,
) -> CopyObjectResult:
    result = object_copies.copy_object(
        uow.session,
        source_bucket=source_bucket,
        source_key=source_key,
        dest_bucket=dest_bucket,
        dest_key=dest_key,
        ingest_meta=ingest_meta,
        metadata_directive=metadata_directive,
        current_user=current_user,
    )
    uow.cache.invalidate_list_objects()
    uow.cache.invalidate_folder_hotpath(uow.session)
    return result


def touch_blob_access(uow: UnitOfWork, blob) -> bool:
    return uow.blobs.touch_access(blob)


def create_multipart_upload(
    uow: UnitOfWork,
    *,
    bucket_name: str,
    key: str,
    ingest_meta: dict,
    current_user: User,
) -> MultipartUpload:
    return object_multipart.create_multipart_upload(
        uow.session,
        multipart_store=uow.multipart,
        bucket_name=bucket_name,
        key=key,
        ingest_meta=ingest_meta,
        current_user=current_user,
    )


def upload_part(
    uow: UnitOfWork,
    *,
    upload_id,
    bucket_name: str,
    key: str,
    part_number: int,
    body: BinaryIO,
    content_hash: bytes,
    content_md5: bytes,
    size_bytes: int,
    current_user: User,
) -> UploadedPart:
    return object_multipart.upload_part(
        uow.session,
        storage=uow.storage,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        part_number=part_number,
        body=body,
        content_hash=content_hash,
        content_md5=content_md5,
        size_bytes=size_bytes,
        current_user=current_user,
    )


def complete_multipart_upload(
    uow: UnitOfWork,
    *,
    upload_id,
    bucket_name: str,
    key: str,
    requested_parts: list[CompleteMultipartPart],
    current_user: User,
) -> CompleteMultipartResult:
    result = object_multipart.complete_multipart_upload(
        uow.session,
        storage=uow.storage,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        requested_parts=requested_parts,
        current_user=current_user,
    )
    uow.cache.invalidate_list_objects()
    uow.cache.invalidate_folder_hotpath(uow.session)
    return result


def abort_multipart_upload(
    uow: UnitOfWork,
    *,
    upload_id,
    bucket_name: str,
    key: str,
    current_user: User,
) -> None:
    object_multipart.abort_multipart_upload(
        uow.session,
        storage=uow.storage,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
    )


def list_multipart_uploads(
    uow: UnitOfWork,
    *,
    bucket_name: str,
    current_user: User,
) -> MultipartUploadListPage:
    return object_multipart.list_multipart_uploads(
        uow.session,
        bucket_name=bucket_name,
        current_user=current_user,
    )


def list_multipart_parts(
    uow: UnitOfWork,
    *,
    upload_id,
    bucket_name: str,
    key: str,
    current_user: User,
) -> MultipartPartListPage:
    return object_multipart.list_multipart_parts(
        uow.session,
        upload_id=upload_id,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
    )


def abort_incomplete_uploads_older_than(uow: UnitOfWork, cutoff) -> int:
    return object_multipart.abort_incomplete_uploads_older_than(
        uow.session,
        cutoff,
        storage=uow.storage,
    )
