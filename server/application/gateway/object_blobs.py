import datetime as dt
import hashlib
import io
from typing import BinaryIO

from domain.blobs.sniff import sniff_blob_attributes
from domain.exceptions import BadRequestError, ConflictError
from infra.db.models import Blob, Bucket
from ports.storage_registry import StorageRegistry
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.gateway import blob_storage
from application.gateway.object_types import CreateBlobResult
from application.control_plane.placement import adjust_bucket_usage_cache
from utils.timing import elapsed_ms, timer_start


def ensure_file_name_available(db: Session, folder_id, file_name: str) -> None:
    from infra.db.models import File

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
    storage: StorageRegistry,
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
    blob_storage.upload_blob(
        storage=storage,
        bucket=bucket,
        bucket_key=blob.bucket_key,
        body=body,
    )
    remote_latency_ms = elapsed_ms(remote_started, minimum=0)

    adjust_bucket_usage_cache(
        bucket.id, object_count_delta=1, size_bytes_delta=size_bytes
    )
    return CreateBlobResult(blob=blob, remote_latency_ms=remote_latency_ms)


def build_blob_bucket_key(blob: Blob) -> str:
    created_at = blob.created_at or dt.datetime.now(dt.UTC)
    return f"{created_at:%Y/%m/%d}/{blob.id}"
