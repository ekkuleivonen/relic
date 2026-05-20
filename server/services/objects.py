import datetime as dt
import hashlib
import io
import posixpath
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, BinaryIO

import boto3
import settings as S
from botocore.exceptions import BotoCoreError, ClientError
from constants import (
    S3_METADATA_DIRECTIVE_COPY,
    S3_METADATA_DIRECTIVE_REPLACE,
)
from enums import Permission
from domain.blobs.sniff import sniff_blob_attributes
from domain.exceptions import BadRequestError, ConflictError, ResourceNotFound
from domain.files.meta import normalize_ingest_meta
from models import Blob, Bucket, File, Folder, User
from sqlalchemy import select
from sqlalchemy.orm import Session
from utils.logging import get_logger

from services import folder_access as folder_access_service
from utils.timing import elapsed_ms, timer_start
from services.placement import (
    adjust_bucket_usage_cache,
    choose_bucket,
    effective_preferred_bucket_id,
)
from services.s3_hotpath_cache import clear_list_objects_response_cache

log = get_logger(__name__)


@dataclass(frozen=True)
class PutObjectResult:
    file: File
    blob: Blob
    etag: str


@dataclass(frozen=True)
class CopyObjectResult:
    file: File
    blob: Blob
    etag: str


@dataclass(frozen=True)
class GetObjectResult:
    file: File
    blob: Blob
    bucket: Bucket


@dataclass(frozen=True)
class GetObjectBytesResult:
    result: GetObjectResult
    boto_response: dict[str, Any]


@dataclass(frozen=True)
class DeleteObjectResult:
    """Result of a DELETE call. existed=False when the key was already absent."""

    existed: bool


@dataclass(frozen=True)
class CreateBlobResult:
    blob: Blob
    remote_latency_ms: int


def put_object(
    db: Session,
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
    folder, file_name = resolve_object_path(
        db,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
    )
    folder_access_service.require_folder_permission_strict(
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
    digest_hex = digest.hex()
    blob = db.scalar(select(Blob).where(Blob.content_hash == digest, Blob.refcount > 0))

    if blob:
        if existing_file is None or existing_file.blob_id != blob.id:
            blob.refcount += 1
    else:
        bucket = choose_bucket(
            db,
            size_bytes=object_size,
            preferred_bucket_id=effective_preferred_bucket_id(db, folder),
        )
        created_blob = create_blob(
            db,
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
    db.commit()
    db.refresh(file)
    db.refresh(blob)
    clear_list_objects_response_cache()
    return PutObjectResult(file=file, blob=blob, etag=digest_hex)


def resolve_object_path(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User,
) -> tuple[Folder, str]:
    normalized_key = normalize_key(key)
    parts = [
        part for part in PurePosixPath(normalized_key).parts if part not in ("", ".")
    ]
    if not parts:
        raise BadRequestError("Object key must include a file name")

    root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))
    if not root:
        raise ResourceNotFound("Root folder not found")

    bucket_folder = db.scalar(
        select(Folder).where(Folder.parent_id == root.id, Folder.name == bucket_name)
    )
    if not bucket_folder:
        raise ResourceNotFound("Bucket folder not found")

    parent = bucket_folder
    for folder_name in parts[:-1]:
        parent = get_or_create_child_folder(
            db,
            parent=parent,
            name=folder_name,
            current_user=current_user,
        )
    return parent, parts[-1]


def normalize_key(key: str) -> str:
    normalized_key = posixpath.normpath(key)
    if normalized_key.startswith("../") or normalized_key == "..":
        raise BadRequestError("Object key cannot escape the bucket")
    return normalized_key


def get_or_create_child_folder(
    db: Session,
    *,
    parent: Folder,
    name: str,
    current_user: User,
) -> Folder:
    child = db.scalar(
        select(Folder).where(Folder.parent_id == parent.id, Folder.name == name)
    )
    if child:
        return child

    folder_access_service.require_folder_permission_strict(
        db,
        current_user,
        parent.id,
        Permission.WRITE,
    )

    child = Folder(
        parent_id=parent.id,
        name=name,
    )
    db.add(child)
    db.flush()
    folder_access_service.clear_hotpath_cache(db)
    return child


def ensure_file_name_available(db: Session, folder_id, file_name: str) -> None:
    existing = db.scalar(
        select(File).where(File.folder_id == folder_id, File.name == file_name)
    )
    if existing:
        raise ConflictError("File already exists")


def prepare_body(
    *,
    body: bytes | BinaryIO,
    content_hash: bytes | None,
    size_bytes: int | None,
) -> tuple[BinaryIO, bytes, int]:
    if isinstance(body, bytes):
        digest = content_hash or hashlib.sha256(body).digest()
        object_size = size_bytes if size_bytes is not None else len(body)
        return io.BytesIO(body), digest, object_size

    if content_hash is None or size_bytes is None:
        raise BadRequestError("Streaming uploads must provide content hash and size")

    body.seek(0)
    return body, content_hash, size_bytes


def create_blob(
    db: Session,
    *,
    bucket: Bucket,
    digest: bytes,
    body: BinaryIO,
    size_bytes: int,
    filename: str,
) -> CreateBlobResult:
    mimetype, extension, size_bytes = sniff_blob_attributes(
        body=body,
        filename=filename,
        size_bytes=size_bytes,
    )
    blob = Blob(
        bucket_id=bucket.id,
        bucket_key="",
        content_hash=digest,
        size_bytes=size_bytes,
        mimetype=mimetype,
        extension=extension,
        refcount=1,
    )
    db.add(blob)
    db.flush()

    blob.bucket_key = build_blob_bucket_key(blob)
    remote_started = timer_start()
    upload_blob(bucket=bucket, bucket_key=blob.bucket_key, body=body)
    remote_latency_ms = elapsed_ms(remote_started, minimum=0)

    adjust_bucket_usage_cache(
        bucket.id, object_count_delta=1, size_bytes_delta=size_bytes
    )
    return CreateBlobResult(blob=blob, remote_latency_ms=remote_latency_ms)


def build_blob_bucket_key(blob: Blob) -> str:
    created_at = blob.created_at or dt.datetime.now(dt.UTC)
    return f"{created_at:%Y/%m/%d}/{blob.id}"


def upload_blob(*, bucket: Bucket, bucket_key: str, body: BinaryIO) -> None:
    try:
        body.seek(0)
        client = boto3.client(
            service_name="s3",
            endpoint_url=bucket.endpoint,
            region_name=bucket.region,
            aws_access_key_id=bucket.key_id,
            aws_secret_access_key=bucket.secret_access_key,
        )
        client.put_object(Bucket=bucket.bucket, Key=bucket_key, Body=body)
    except (BotoCoreError, ClientError) as exc:
        log.warning(
            "blob_upload_failed",
            bucket_id=str(bucket.id),
            bucket_name=bucket.name,
            endpoint=bucket.endpoint,
            remote_bucket=bucket.bucket,
            error=str(exc),
        )
        raise BadRequestError("Failed to upload object to bucket") from exc


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def delete_object(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
) -> DeleteObjectResult:
    """
    Delete a File by bucket+key and decrement the Blob refcount.

    refcount == 0 means the Blob is logically dereferenced and will be deleted
    (including backing object-store bytes and bucket counters) by the periodic
    arq storage maintenance purge job—not on this API path.

    S3 DELETE is idempotent: missing keys still return success. We mirror that
    so external clients (DuckLake, rclone) get the contract they expect.
    """
    folder, file_name = resolve_existing_object_path(
        db, bucket_name=bucket_name, key=key
    )
    if folder is None:
        return DeleteObjectResult(existed=False)

    if current_user is not None:
        folder_access_service.require_folder_permission_strict(
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

    db.commit()
    clear_list_objects_response_cache()
    return DeleteObjectResult(existed=True)


def delete_blob_bytes(*, bucket: Bucket, bucket_key: str) -> None:
    try:
        client = boto3.client(
            service_name="s3",
            endpoint_url=bucket.endpoint,
            region_name=bucket.region,
            aws_access_key_id=bucket.key_id,
            aws_secret_access_key=bucket.secret_access_key,
        )
        client.delete_object(Bucket=bucket.bucket, Key=bucket_key)
    except (BotoCoreError, ClientError) as exc:
        raise BadRequestError("Failed to delete object bytes") from exc


# ---------------------------------------------------------------------------
# COPY
# ---------------------------------------------------------------------------


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
    """
    S3 CopyObject - metadata-only copy. The new File points at the same Blob;
    refcount on the Blob is incremented.
    """
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

    folder_access_service.require_folder_permission_strict(
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

    folder_access_service.require_folder_permission_strict(
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
    db.commit()
    db.refresh(new_file)
    db.refresh(blob)
    clear_list_objects_response_cache()

    etag = blob.content_hash.hex()
    return CopyObjectResult(file=new_file, blob=blob, etag=etag)


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


def get_object(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
) -> GetObjectResult:
    """Resolve a File by bucket+key for download. READ permission required."""
    folder, file_name = require_existing_object_path(
        db, bucket_name=bucket_name, key=key
    )
    file = db.scalar(
        select(File).where(File.folder_id == folder.id, File.name == file_name)
    )
    if file is None:
        raise ResourceNotFound("Object not found")

    if current_user is not None:
        folder_access_service.require_folder_permission_strict(
            db, current_user, folder.id, Permission.READ
        )

    blob = db.get(Blob, file.blob_id)
    if blob is None:
        raise ResourceNotFound("Object bytes not found")

    bucket = db.get(Bucket, blob.bucket_id)
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
    bucket_name: str,
    key: str,
    range_header: str | None = None,
    current_user: User | None = None,
) -> GetObjectBytesResult:
    result = get_object(db, bucket_name=bucket_name, key=key, current_user=current_user)
    boto_response = fetch_blob_bytes(
        bucket=result.bucket,
        bucket_key=result.blob.bucket_key,
        range_header=range_header,
    )
    return GetObjectBytesResult(result=result, boto_response=boto_response)


def touch_blob_access(
    db: Session,
    blob: Blob,
    *,
    now: dt.datetime | None = None,
    debounce_minutes: int | None = None,
) -> bool:
    """Bump ``Blob.accessed_at`` to ``now`` if more than ``debounce_minutes`` old.

    Called from every read code path (S3 GetObject, HeadObject, presign-download
    issuance) so the maintenance cron has an accurate "last touched" signal for
    promote/demote decisions. Debouncing keeps high-QPS lakehouse traffic
    (e.g. catalog HEADs against parquet files) from beating the blobs row to
    death.

    Returns True if the row was updated, False if the call was debounced.
    Caller is responsible for committing.
    """
    effective_now = now or dt.datetime.now(dt.UTC)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=dt.UTC)
    effective_debounce = (
        debounce_minutes
        if debounce_minutes is not None
        else S.ACCESS_TOUCH_DEBOUNCE_MINUTES
    )

    last = blob.accessed_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=dt.UTC)
        if (effective_now - last) < dt.timedelta(minutes=effective_debounce):
            return False

    blob.accessed_at = effective_now
    db.flush()
    return True


def fetch_blob_bytes(
    *,
    bucket: Bucket,
    bucket_key: str,
    range_header: str | None = None,
) -> dict[str, Any]:
    """
    Fetch a blob from the underlying bucket via boto3. Returns the raw boto3
    response dict so callers can stream `Body` and pass through metadata.
    """
    try:
        client = boto3.client(
            service_name="s3",
            endpoint_url=bucket.endpoint,
            region_name=bucket.region,
            aws_access_key_id=bucket.key_id,
            aws_secret_access_key=bucket.secret_access_key,
        )
        params: dict = {"Bucket": bucket.bucket, "Key": bucket_key}
        if range_header:
            params["Range"] = range_header
        return client.get_object(**params)
    except (BotoCoreError, ClientError) as exc:
        raise BadRequestError("Failed to fetch object bytes") from exc


# ---------------------------------------------------------------------------
# Path resolution helpers (read-only, do not auto-create folders)
# ---------------------------------------------------------------------------


def resolve_existing_object_path(
    db: Session,
    *,
    bucket_name: str,
    key: str,
) -> tuple[Folder | None, str]:
    """
    Resolve an existing folder + filename for bucket+key, without creating
    intermediate folders. Returns (None, "") if any segment is missing.
    """
    normalized_key = normalize_key(key)
    parts = [
        part for part in PurePosixPath(normalized_key).parts if part not in ("", ".")
    ]
    if not parts:
        return None, ""

    root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))
    if not root:
        return None, ""

    bucket_folder = db.scalar(
        select(Folder).where(Folder.parent_id == root.id, Folder.name == bucket_name)
    )
    if not bucket_folder:
        return None, ""

    parent = bucket_folder
    for folder_name in parts[:-1]:
        child = db.scalar(
            select(Folder).where(
                Folder.parent_id == parent.id, Folder.name == folder_name
            )
        )
        if child is None:
            return None, ""
        parent = child

    return parent, parts[-1]


def require_existing_object_path(
    db: Session,
    *,
    bucket_name: str,
    key: str,
) -> tuple[Folder, str]:
    folder, file_name = resolve_existing_object_path(
        db, bucket_name=bucket_name, key=key
    )
    if folder is None:
        raise ResourceNotFound("Object not found")
    return folder, file_name


def get_file_for_user(
    db: Session,
    file_id,
    user: User,
    permission: Permission,
) -> File:
    file = db.get(File, file_id)
    if file is None:
        raise ResourceNotFound("File not found")
    folder_access_service.require_folder_permission_strict(
        db, user, file.folder_id, permission
    )
    return file


def build_bucket_and_key_for_file(db: Session, file: File) -> tuple[str, str]:
    """Compose (bucket_name, key) the gateway uses to identify a File."""
    folder_path = folder_access_service.resolve_folder_path(
        db, db.get(Folder, file.folder_id)
    )
    parts = [part for part in folder_path.split("/") if part]
    if not parts:
        raise BadRequestError("File is not under a bucket folder")
    bucket = parts[0]
    key_parts = [*parts[1:], file.name]
    return bucket, "/".join(key_parts)


def build_bucket_and_key_for_destination(
    db: Session,
    *,
    folder: Folder,
    filename: str,
) -> tuple[str, str]:
    if "/" in filename:
        raise BadRequestError("Filename cannot contain '/'")
    folder_path = folder_access_service.resolve_folder_path(db, folder)
    parts = [part for part in folder_path.split("/") if part]
    if not parts:
        raise BadRequestError("Cannot place files in the root folder")
    bucket = parts[0]
    key_parts = [*parts[1:], filename]
    return bucket, "/".join(key_parts)
