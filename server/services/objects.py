import datetime as dt
import hashlib
import io
import posixpath
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, BinaryIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from file_meta import build_file_meta, validate_file_meta_dict
from managers.exceptions import BadRequestError, ConflictError, ResourceNotFound
from models import Blob, Bucket, File, Folder, PARSE_STATUS_PENDING, User
from schema_plan import BucketTier, Permission
from services import folder_access as folder_access_service
from services.events import (
    EventContext,
    create_event,
    elapsed_ms,
    latency_metadata,
    timer_start,
)
from services.folder_storage_policy import effective_min_tier
from services.placement import adjust_bucket_usage_cache, choose_bucket
from utils.logging import get_logger

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


METADATA_DIRECTIVE_COPY = "COPY"
METADATA_DIRECTIVE_REPLACE = "REPLACE"


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
    event_context: EventContext | None = None,
) -> PutObjectResult:
    started_at = timer_start()
    db_latency_ms = 0
    remote_latency_ms = 0
    db_started = timer_start()
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
    ensure_file_name_available(db, folder.id, file_name)
    db_latency_ms += elapsed_ms(db_started, minimum=0)

    body_file, digest, object_size = prepare_body(
        body=body,
        content_hash=content_hash,
        size_bytes=size_bytes,
    )
    digest_hex = digest.hex()
    db_started = timer_start()
    blob = db.scalar(
        select(Blob).where(Blob.content_hash == digest, Blob.refcount > 0)
    )

    if blob:
        blob.refcount += 1
    else:
        bucket = choose_bucket(
            db,
            tier=BucketTier(effective_min_tier(db, folder)),
            size_bytes=object_size,
        )
        db_latency_ms += elapsed_ms(db_started, minimum=0)
        created_blob = create_blob(
            db,
            bucket=bucket,
            digest=digest,
            body=body_file,
            size_bytes=object_size,
        )
        blob = created_blob.blob
        remote_latency_ms += created_blob.remote_latency_ms
        db_started = timer_start()

    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        uploaded_by=current_user.id,
        name=file_name,
        parse_status=PARSE_STATUS_PENDING,
        meta=build_file_meta(
            file_name=file_name,
            size=object_size,
            user_meta=ingest_meta,
        ),
    )
    db.add(file)
    db.flush()
    db_latency_ms += elapsed_ms(db_started, minimum=0)
    if event_context is not None:
        create_event(
            db,
            source=event_context.source,
            operation="object.put",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            file_ids=[file.id],
            folder_ids=[file.folder_id],
            blob_ids=[blob.id],
            metadata={
                "bucket": bucket_name,
                "key": key,
                "etag": digest_hex,
                "size_bytes": blob.size_bytes,
                **latency_metadata(
                    started_at,
                    db_latency_ms=db_latency_ms,
                    remote_latency_ms=remote_latency_ms,
                ),
            },
        )
    db.commit()
    db.refresh(file)
    db.refresh(blob)
    return PutObjectResult(file=file, blob=blob, etag=digest_hex)


def resolve_object_path(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
) -> tuple[Folder, str]:
    normalized_key = normalize_key(key)
    parts = [part for part in PurePosixPath(normalized_key).parts if part not in ("", ".")]
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
    current_user: User | None = None,
) -> Folder:
    child = db.scalar(
        select(Folder).where(Folder.parent_id == parent.id, Folder.name == name)
    )
    if child:
        return child

    if current_user is not None:
        folder_access_service.require_folder_permission_strict(
            db,
            current_user,
            parent.id,
            Permission.WRITE,
        )

        child = Folder(
            parent_id=parent.id,
            name=name,
            cooldown_days=None,
            min_tier=None,
        )
    db.add(child)
    db.flush()
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
) -> CreateBlobResult:
    blob = Blob(
        bucket_id=bucket.id,
        bucket_key="",
        content_hash=digest,
        size_bytes=size_bytes,
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
    event_context: EventContext | None = None,
) -> DeleteObjectResult:
    """
    Delete a File by bucket+key and decrement the Blob refcount.

    refcount == 0 means the Blob is logically dereferenced and will be deleted
    (including backing object-store bytes and bucket counters) by the periodic
    arq storage maintenance purge job—not on this API path.

    S3 DELETE is idempotent: missing keys still return success. We mirror that
    so external clients (DuckLake, rclone) get the contract they expect.
    """
    started_at = timer_start()
    db_latency_ms = 0
    db_started = timer_start()
    folder, file_name = resolve_existing_object_path(
        db, bucket_name=bucket_name, key=key
    )
    db_latency_ms += elapsed_ms(db_started, minimum=0)
    if folder is None:
        if event_context is not None:
            create_event(
                db,
                source=event_context.source,
                operation="object.deleted",
                actor_user_id=event_context.actor_user_id,
                request_id=event_context.request_id,
                metadata={
                    "bucket": bucket_name,
                    "key": key,
                    "existed": False,
                    **latency_metadata(started_at, db_latency_ms=db_latency_ms),
                },
            )
            db.commit()
        return DeleteObjectResult(existed=False)

    if current_user is not None:
        db_started = timer_start()
        folder_access_service.require_folder_permission_strict(
            db,
            current_user,
            folder.id,
            Permission.DELETE,
        )
        db_latency_ms += elapsed_ms(db_started, minimum=0)

    db_started = timer_start()
    file = db.scalar(
        select(File).where(File.folder_id == folder.id, File.name == file_name)
    )
    db_latency_ms += elapsed_ms(db_started, minimum=0)
    if file is None:
        if event_context is not None:
            create_event(
                db,
                source=event_context.source,
                operation="object.deleted",
                actor_user_id=event_context.actor_user_id,
                request_id=event_context.request_id,
                folder_ids=[folder.id],
                metadata={
                    "bucket": bucket_name,
                    "key": key,
                    "existed": False,
                    **latency_metadata(started_at, db_latency_ms=db_latency_ms),
                },
            )
            db.commit()
        return DeleteObjectResult(existed=False)

    db_started = timer_start()
    blob = db.get(Blob, file.blob_id)
    file_id = file.id
    folder_id = file.folder_id
    blob_id = file.blob_id
    db.delete(file)
    db.flush()

    if blob is not None:
        blob.refcount -= 1
        if blob.refcount < 0:
            blob.refcount = 0
    db_latency_ms += elapsed_ms(db_started, minimum=0)

    if event_context is not None:
        create_event(
            db,
            source=event_context.source,
            operation="object.deleted",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            file_ids=[file_id],
            folder_ids=[folder_id],
            blob_ids=[blob_id],
            metadata={
                "bucket": bucket_name,
                "key": key,
                "existed": True,
                **latency_metadata(started_at, db_latency_ms=db_latency_ms),
            },
        )
    db.commit()
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
    metadata_directive: str = METADATA_DIRECTIVE_COPY,
    current_user: User,
    event_context: EventContext | None = None,
) -> CopyObjectResult:
    """
    S3 CopyObject - metadata-only copy. The new File points at the same Blob;
    refcount on the Blob is incremented.
    """
    started_at = timer_start()
    db_latency_ms = 0
    if metadata_directive not in (METADATA_DIRECTIVE_COPY, METADATA_DIRECTIVE_REPLACE):
        raise BadRequestError(
            "x-amz-metadata-directive must be COPY or REPLACE"
        )

    db_started = timer_start()
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
        and metadata_directive == METADATA_DIRECTIVE_COPY
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
    db_latency_ms += elapsed_ms(db_started, minimum=0)

    copied_meta = (
        validate_file_meta_dict(dict(source_file.meta)).model_dump(mode="json")
        if metadata_directive == METADATA_DIRECTIVE_COPY
        else build_file_meta(
            file_name=dest_file_name,
            size=blob.size_bytes,
            user_meta=ingest_meta,
        )
    )

    new_file = File(
        folder_id=dest_folder.id,
        blob_id=blob.id,
        uploaded_by=current_user.id,
        name=dest_file_name,
        parse_status=PARSE_STATUS_PENDING,
        meta=copied_meta,
    )
    db.add(new_file)
    blob.refcount += 1
    db_started = timer_start()
    db.flush()
    db_latency_ms += elapsed_ms(db_started, minimum=0)
    if event_context is not None:
        create_event(
            db,
            source=event_context.source,
            operation="object.copied",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            file_ids=[new_file.id],
            folder_ids=[source_folder.id, dest_folder.id],
            blob_ids=[blob.id],
            metadata={
                "bucket": dest_bucket,
                "key": dest_key,
                "source_bucket": source_bucket,
                "source_key": source_key,
                "metadata_directive": metadata_directive,
                "etag": blob.content_hash.hex(),
                **latency_metadata(started_at, db_latency_ms=db_latency_ms),
            },
        )
    db.commit()
    db.refresh(new_file)
    db.refresh(blob)

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
    event_context: EventContext | None = None,
) -> GetObjectResult:
    started_at = timer_start()
    db_started = timer_start()
    result = get_object(
        db, bucket_name=bucket_name, key=key, current_user=current_user
    )
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    if event_context is not None:
        create_event(
            db,
            source=event_context.source,
            operation="object.head",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            file_ids=[result.file.id],
            folder_ids=[result.file.folder_id],
            blob_ids=[result.blob.id],
            metadata={
                "bucket": bucket_name,
                "key": key,
                **latency_metadata(started_at, db_latency_ms=db_latency_ms),
            },
        )
        db.commit()
    return result


def get_object_bytes(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    range_header: str | None = None,
    current_user: User | None = None,
    event_context: EventContext | None = None,
) -> GetObjectBytesResult:
    started_at = timer_start()
    db_started = timer_start()
    result = get_object(
        db, bucket_name=bucket_name, key=key, current_user=current_user
    )
    db_latency_ms = elapsed_ms(db_started, minimum=0)
    remote_started = timer_start()
    boto_response = fetch_blob_bytes(
        bucket=result.bucket,
        bucket_key=result.blob.bucket_key,
        range_header=range_header,
    )
    remote_latency_ms = elapsed_ms(remote_started, minimum=0)
    if event_context is not None:
        create_event(
            db,
            source=event_context.source,
            operation="object.get",
            actor_user_id=event_context.actor_user_id,
            request_id=event_context.request_id,
            file_ids=[result.file.id],
            folder_ids=[result.file.folder_id],
            blob_ids=[result.blob.id],
            metadata={
                "bucket": bucket_name,
                "key": key,
                "range": range_header,
                "content_length": boto_response.get("ContentLength"),
                **latency_metadata(
                    started_at,
                    db_latency_ms=db_latency_ms,
                    remote_latency_ms=remote_latency_ms,
                ),
            },
        )
        db.commit()
    return GetObjectBytesResult(result=result, boto_response=boto_response)


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
    parts = [part for part in PurePosixPath(normalized_key).parts if part not in ("", ".")]
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
