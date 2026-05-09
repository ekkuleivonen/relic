import mimetypes
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

import settings
from file_meta import build_file_meta, merge_parser_meta, validate_file_meta_dict
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

        maybe_run_toolchain(
            parser_meta=parser_meta,
            file_id=file_id,
            mime_type=parser_meta["mimetype"],
            bucket=bucket,
            blob=blob,
            prefix=prefix,
        )

        validate_parser_meta(parser_meta=parser_meta)
        file.meta = parser_meta
        file.parse_status = PARSE_STATUS_COMPLETED
        db.commit()
        db.refresh(file)
        return file
    except Exception:
        file.parse_status = PARSE_STATUS_FAILED
        db.commit()
        raise


def build_base_parser_meta(*, file: File, blob: Blob, prefix: bytes) -> dict:
    existing = dict(file.meta)
    if not existing:
        existing = build_file_meta(file_name=file.name, size=blob.size_bytes, user_meta={})
    detected_meta = build_file_meta(
        file_name=file.name,
        size=blob.size_bytes,
        user_meta={},
        mimetype=detect_mime_type(prefix=prefix, filename=file.name),
    )
    return merge_parser_meta(existing=existing, parsed=detected_meta)


def validate_parser_meta(*, parser_meta: dict) -> None:
    try:
        validate_file_meta_dict(parser_meta)
    except ValidationError as exc:
        raise ValueError(f"Parser metadata invalid: {exc}") from exc


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


def maybe_run_toolchain(
    *,
    parser_meta: dict,
    file_id: uuid.UUID,
    mime_type: str,
    bucket: Bucket,
    blob: Blob,
    prefix: bytes,
) -> None:
    try:
        if mime_type.startswith("image/"):
            from parsers.toolchains.image import parse_image

            cap = settings.IMAGE_PARSE_MAX_BYTES
            content = read_blob_bytes_capped(
                bucket=bucket,
                bucket_key=blob.bucket_key,
                size_bytes=blob.size_bytes,
                max_bytes=cap,
            )
            if len(content) < blob.size_bytes:
                log.info(
                    "image_parse_truncated",
                    file_id=str(file_id),
                    read_bytes=len(content),
                    blob_size=blob.size_bytes,
                    max_bytes=cap,
                )
            parsed = parse_image(content=content, existing_meta=parser_meta)
            merged = merge_parser_meta(existing=parser_meta, parsed=parsed)
            parser_meta.clear()
            parser_meta.update(merged)
        elif mime_type == "text/csv":
            from parsers.toolchains.csv import parse_csv

            cap = settings.TABULAR_PARSE_MAX_BYTES
            content = read_blob_bytes_capped(
                bucket=bucket,
                bucket_key=blob.bucket_key,
                size_bytes=blob.size_bytes,
                max_bytes=cap,
            )
            if len(content) < blob.size_bytes:
                log.info(
                    "tabular_parse_truncated",
                    file_id=str(file_id),
                    read_bytes=len(content),
                    blob_size=blob.size_bytes,
                    max_bytes=cap,
                    mime_type=mime_type,
                )
            parsed = parse_csv(content=content, existing_meta=parser_meta)
            merged = merge_parser_meta(existing=parser_meta, parsed=parsed)
            parser_meta.clear()
            parser_meta.update(merged)
        elif is_json_file(mime_type=mime_type, parser_meta=parser_meta):
            from parsers.toolchains.json import parse_json

            cap = settings.JSON_PARSE_MAX_BYTES
            content = read_blob_bytes_capped(
                bucket=bucket,
                bucket_key=blob.bucket_key,
                size_bytes=blob.size_bytes,
                max_bytes=cap,
            )
            if len(content) < blob.size_bytes:
                log.info(
                    "json_parse_truncated",
                    file_id=str(file_id),
                    read_bytes=len(content),
                    blob_size=blob.size_bytes,
                    max_bytes=cap,
                    mime_type=mime_type,
                )
            parsed = parse_json(content=content, existing_meta=parser_meta)
            merged = merge_parser_meta(existing=parser_meta, parsed=parsed)
            parser_meta.clear()
            parser_meta.update(merged)
        elif mime_type == "application/pdf":
            from parsers.toolchains.pdf import parse_pdf

            cap = settings.PDF_PARSE_MAX_BYTES
            content = read_blob_bytes_capped(
                bucket=bucket,
                bucket_key=blob.bucket_key,
                size_bytes=blob.size_bytes,
                max_bytes=cap,
            )
            if len(content) < blob.size_bytes:
                log.info(
                    "pdf_parse_truncated",
                    file_id=str(file_id),
                    read_bytes=len(content),
                    blob_size=blob.size_bytes,
                    max_bytes=cap,
                    mime_type=mime_type,
                )
            parsed = parse_pdf(content=content, existing_meta=parser_meta)
            merged = merge_parser_meta(existing=parser_meta, parsed=parsed)
            parser_meta.clear()
            parser_meta.update(merged)
        elif mime_type == "application/vnd.apache.parquet":
            from parsers.toolchains.parquet import parse_parquet

            parse_parquet(prefix=prefix)
    except NotImplementedError as exc:
        log.warning(
            "parser_toolchain_not_implemented",
            file_id=str(file_id),
            mime_type=mime_type,
            error=str(exc),
        )


def is_json_file(*, mime_type: str, parser_meta: dict) -> bool:
    if mime_type in {
        "application/json",
        "application/geo+json",
        "application/x-ndjson",
        "application/jsonl",
    }:
        return True
    return parser_meta.get("extension") in {"json", "jsonl", "geojson", "ipynb"}


def read_blob_prefix(*, bucket: Bucket, bucket_key: str) -> bytes:
    if PREFIX_BYTES <= 0:
        return b""
    response = object_service.fetch_blob_bytes(
        bucket=bucket,
        bucket_key=bucket_key,
        range_header=f"bytes=0-{PREFIX_BYTES - 1}",
    )
    return response["Body"].read(PREFIX_BYTES)


def read_blob_bytes_capped(
    *,
    bucket: Bucket,
    bucket_key: str,
    size_bytes: int,
    max_bytes: int,
) -> bytes:
    if max_bytes <= 0 or size_bytes <= 0:
        return b""
    n = min(size_bytes, max_bytes)
    response = object_service.fetch_blob_bytes(
        bucket=bucket,
        bucket_key=bucket_key,
        range_header=f"bytes=0-{n - 1}",
    )
    return response["Body"].read(n)


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
