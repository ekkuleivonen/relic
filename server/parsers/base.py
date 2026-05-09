import mimetypes
import uuid
from pathlib import PurePosixPath

from jsonschema import ValidationError, validate
from sqlalchemy.orm import Session

from managers.exceptions import ResourceNotFound
from models import (
    Blob,
    Bucket,
    File,
    PARSE_STATUS_COMPLETED,
    PARSE_STATUS_FAILED,
    PARSE_STATUS_IN_PROGRESS,
)
from services import objects as object_service
from utils.logging import get_logger

log = get_logger(__name__)

PREFIX_BYTES = 4096


def parse_file(db: Session, file_id: uuid.UUID) -> File:
    file = require_file(db, file_id)
    file.parse_status = PARSE_STATUS_IN_PROGRESS
    db.commit()

    try:
        blob = require_blob(db, file.blob_id)
        bucket = require_bucket(db, blob.bucket_id)
        prefix = read_blob_prefix(bucket=bucket, bucket_key=blob.bucket_key)
        parser_meta = build_base_parser_meta(file=file, blob=blob, prefix=prefix)

        maybe_run_toolchain(file_id=file_id, mime_type=parser_meta["file"]["mime_type"], prefix=prefix)

        validate_parser_meta(file=file, parser_meta=parser_meta)
        file.parser_meta = parser_meta
        file.parse_status = PARSE_STATUS_COMPLETED
        db.commit()
        db.refresh(file)
        return file
    except Exception:
        file.parse_status = PARSE_STATUS_FAILED
        db.commit()
        raise


def build_base_parser_meta(*, file: File, blob: Blob, prefix: bytes) -> dict:
    extension = PurePosixPath(file.name).suffix.removeprefix(".").lower()
    return {
        "file": {
            "original_filename": file.ingest_meta.get("original_filename", file.name),
            "mime_type": detect_mime_type(prefix=prefix, filename=file.name),
            "size": blob.size_bytes,
            "extension": extension,
        }
    }


def validate_parser_meta(*, file: File, parser_meta: dict) -> None:
    try:
        validate(instance=parser_meta, schema=file.folder.schema)
    except ValidationError as exc:
        raise ValueError(f"Parser metadata failed folder schema: {exc.message}") from exc


def detect_mime_type(*, prefix: bytes, filename: str) -> str:
    signature = detect_signature_mime_type(prefix)
    if signature:
        return signature
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def detect_signature_mime_type(prefix: bytes) -> str | None:
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"PK\x03\x04"):
        return "application/zip"
    if prefix.startswith(b"\x1f\x8b"):
        return "application/gzip"
    if prefix.startswith(b"PAR1"):
        return "application/vnd.apache.parquet"
    if prefix.startswith(b"SQLite format 3\x00"):
        return "application/vnd.sqlite3"
    return None


def maybe_run_toolchain(*, file_id: uuid.UUID, mime_type: str, prefix: bytes) -> None:
    try:
        if mime_type.startswith("image/"):
            from parsers.toolchains.image import parse_image

            parse_image(prefix=prefix)
        if mime_type in {"text/csv", "application/vnd.apache.parquet"}:
            from parsers.toolchains.tabular import parse_tabular

            parse_tabular(prefix=prefix)
    except NotImplementedError as exc:
        log.warning(
            "parser_toolchain_not_implemented",
            file_id=str(file_id),
            mime_type=mime_type,
            error=str(exc),
        )


def read_blob_prefix(*, bucket: Bucket, bucket_key: str) -> bytes:
    if PREFIX_BYTES <= 0:
        return b""
    response = object_service.fetch_blob_bytes(
        bucket=bucket,
        bucket_key=bucket_key,
        range_header=f"bytes=0-{PREFIX_BYTES - 1}",
    )
    return response["Body"].read(PREFIX_BYTES)


def require_file(db: Session, file_id: uuid.UUID) -> File:
    file = db.get(File, file_id)
    if file is None:
        raise ResourceNotFound("File not found")
    return file


def require_blob(db: Session, blob_id: uuid.UUID) -> Blob:
    blob = db.get(Blob, blob_id)
    if blob is None:
        raise ResourceNotFound("Blob not found")
    return blob


def require_bucket(db: Session, bucket_id: uuid.UUID) -> Bucket:
    bucket = db.get(Bucket, bucket_id)
    if bucket is None:
        raise ResourceNotFound("Bucket not found")
    return bucket
