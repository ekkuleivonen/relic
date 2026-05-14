"""Metadata extraction primitives used by `MetaExtractProcessor`."""

from __future__ import annotations

import mimetypes
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError
from sqlalchemy.orm import Session

import settings
from constants import META_EXTRACT_PREFIX_BYTES
from domain.exceptions import ResourceNotFound
from domain.files.meta import build_file_meta, merge_parser_meta, validate_file_meta_dict
from enums import MetaExtractStatus
from models import Blob, Bucket, File
from services import objects as object_service
from utils.logging import get_logger

log = get_logger(__name__)

ExtractionStatus = Literal["completed", "stale"]


@dataclass(frozen=True)
class MetaExtractionResult:
    status: ExtractionStatus
    file: File | None = None
    message: str | None = None


@dataclass(frozen=True)
class Toolchain:
    name: str
    max_bytes: int
    matches: Callable[[str, dict], bool]
    parse: Callable[[bytes, dict], dict]


def extract_file_metadata(
    db: Session,
    *,
    file_id: uuid.UUID,
    expected_blob_id: uuid.UUID | None,
) -> MetaExtractionResult:
    """Parse and persist metadata for a file if its input blob is still current."""
    file = require_file(db, file_id)
    if expected_blob_id is not None and file.blob_id != expected_blob_id:
        return MetaExtractionResult(
            status="stale",
            message="file blob changed before metadata extraction started",
        )

    file.meta_extract_status = MetaExtractStatus.IN_PROGRESS
    db.flush()

    try:
        blob = require_blob(db, file.blob_id)
        bucket = require_bucket(db, blob.bucket_id)
        prefix = read_blob_prefix(bucket=bucket, bucket_key=blob.bucket_key)
        parser_meta = build_base_parser_meta(file=file, blob=blob, prefix=prefix)

        run_matching_toolchain(
            parser_meta=parser_meta,
            file_id=file_id,
            mime_type=parser_meta["mimetype"],
            bucket=bucket,
            blob=blob,
        )

        validate_parser_meta(parser_meta=parser_meta)
        if expected_blob_id is not None and file.blob_id != expected_blob_id:
            return MetaExtractionResult(
                status="stale",
                message="file blob changed before metadata extraction finished",
            )

        file.meta = parser_meta
        file.meta_extract_status = MetaExtractStatus.COMPLETED
        db.flush()
        db.refresh(file)
        return MetaExtractionResult(status="completed", file=file)
    except Exception:
        file.meta_extract_status = MetaExtractStatus.FAILED
        db.flush()
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
        raise ValueError(f"Extracted metadata invalid: {exc}") from exc


def detect_mime_type(*, prefix: bytes, filename: str) -> str:
    signature = detect_signature_mime_type(prefix)
    if signature:
        return signature
    lower_name = filename.lower()
    if lower_name.endswith(".parquet"):
        return "application/vnd.apache.parquet"
    if lower_name.endswith((".htm", ".html")):
        return "text/html"
    if lower_name.endswith(".xhtml"):
        return "application/xhtml+xml"
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
    head = prefix.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return "text/html"
    return None


def run_matching_toolchain(
    *,
    parser_meta: dict,
    file_id: uuid.UUID,
    mime_type: str,
    bucket: Bucket,
    blob: Blob,
) -> None:
    for toolchain in _toolchains():
        if not toolchain.matches(mime_type, parser_meta):
            continue
        content = read_blob_bytes_capped(
            bucket=bucket,
            bucket_key=blob.bucket_key,
            size_bytes=blob.size_bytes,
            max_bytes=toolchain.max_bytes,
        )
        if len(content) < blob.size_bytes:
            log.info(
                f"{toolchain.name}_meta_extract_truncated",
                file_id=str(file_id),
                read_bytes=len(content),
                blob_size=blob.size_bytes,
                max_bytes=toolchain.max_bytes,
                mime_type=mime_type,
            )
        try:
            parsed = toolchain.parse(content, parser_meta)
        except NotImplementedError as exc:
            log.warning(
                "meta_extract_toolchain_not_implemented",
                file_id=str(file_id),
                mime_type=mime_type,
                toolchain=toolchain.name,
                error=str(exc),
            )
            return
        merged = merge_parser_meta(existing=parser_meta, parsed=parsed)
        parser_meta.clear()
        parser_meta.update(merged)
        return


def _toolchains() -> tuple[Toolchain, ...]:
    from processors.kinds.meta_extract.toolchains.archive import parse_archive
    from processors.kinds.meta_extract.toolchains.audio import parse_audio
    from processors.kinds.meta_extract.toolchains.csv import parse_csv
    from processors.kinds.meta_extract.toolchains.html import parse_html
    from processors.kinds.meta_extract.toolchains.image import parse_image
    from processors.kinds.meta_extract.toolchains.json import parse_json
    from processors.kinds.meta_extract.toolchains.office_doc import parse_office_doc
    from processors.kinds.meta_extract.toolchains.parquet import parse_parquet
    from processors.kinds.meta_extract.toolchains.pdf import parse_pdf
    from processors.kinds.meta_extract.toolchains.text import parse_text
    from processors.kinds.meta_extract.toolchains.video import parse_video

    return (
        Toolchain(
            name="image",
            max_bytes=settings.IMAGE_META_EXTRACT_MAX_BYTES,
            matches=lambda mime_type, _meta: mime_type.startswith("image/"),
            parse=lambda content, meta: parse_image(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="tabular",
            max_bytes=settings.TABULAR_META_EXTRACT_MAX_BYTES,
            matches=lambda mime_type, _meta: mime_type == "text/csv",
            parse=lambda content, meta: parse_csv(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="json",
            max_bytes=settings.JSON_META_EXTRACT_MAX_BYTES,
            matches=is_json_file,
            parse=lambda content, meta: parse_json(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="pdf",
            max_bytes=settings.PDF_META_EXTRACT_MAX_BYTES,
            matches=lambda mime_type, _meta: mime_type == "application/pdf",
            parse=lambda content, meta: parse_pdf(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="parquet",
            max_bytes=settings.PARQUET_META_EXTRACT_MAX_BYTES,
            matches=is_parquet_file,
            parse=lambda content, meta: parse_parquet(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="audio",
            max_bytes=settings.AUDIO_META_EXTRACT_MAX_BYTES,
            matches=is_audio_file,
            parse=lambda content, meta: parse_audio(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="video",
            max_bytes=settings.VIDEO_META_EXTRACT_MAX_BYTES,
            matches=is_video_file,
            parse=lambda content, meta: parse_video(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="office_doc",
            max_bytes=settings.OFFICE_DOC_META_EXTRACT_MAX_BYTES,
            matches=is_office_doc_file,
            parse=lambda content, meta: parse_office_doc(
                content=content, existing_meta=meta
            ),
        ),
        Toolchain(
            name="html",
            max_bytes=settings.HTML_META_EXTRACT_MAX_BYTES,
            matches=is_html_file,
            parse=lambda content, meta: parse_html(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="archive",
            max_bytes=settings.ARCHIVE_META_EXTRACT_MAX_BYTES,
            matches=is_archive_file,
            parse=lambda content, meta: parse_archive(content=content, existing_meta=meta),
        ),
        Toolchain(
            name="text",
            max_bytes=settings.TEXT_META_EXTRACT_MAX_BYTES,
            matches=is_text_file,
            parse=lambda content, meta: parse_text(content=content, existing_meta=meta),
        ),
    )


def is_json_file(mime_type: str, parser_meta: dict) -> bool:
    if mime_type in {
        "application/json",
        "application/geo+json",
        "application/x-ndjson",
        "application/jsonl",
    }:
        return True
    return parser_meta.get("extension") in {"json", "jsonl", "geojson", "ipynb"}


def is_parquet_file(mime_type: str, parser_meta: dict) -> bool:
    if mime_type == "application/vnd.apache.parquet":
        return True
    return parser_meta.get("extension") == "parquet"


def is_audio_file(mime_type: str, parser_meta: dict) -> bool:
    if mime_type.startswith("audio/"):
        return True
    return parser_meta.get("extension") in {
        "aac",
        "aif",
        "aiff",
        "flac",
        "m4a",
        "mp3",
        "oga",
        "ogg",
        "opus",
        "wav",
    }


def is_video_file(mime_type: str, parser_meta: dict) -> bool:
    if mime_type.startswith("video/"):
        return True
    return parser_meta.get("extension") in {"avi", "mkv", "mov", "mp4", "webm"}


def is_office_doc_file(mime_type: str, parser_meta: dict) -> bool:
    if mime_type in {
        "application/msword",
        "application/rtf",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/rtf",
    }:
        return True
    return parser_meta.get("extension") in {"doc", "docx", "odt", "rtf"}


def is_html_file(mime_type: str, parser_meta: dict) -> bool:
    if mime_type in {"text/html", "application/xhtml+xml"}:
        return True
    return parser_meta.get("extension") in {"htm", "html", "xhtml"}


def is_archive_file(mime_type: str, parser_meta: dict) -> bool:
    if mime_type in {
        "application/gzip",
        "application/tar",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
        "application/x-tar",
        "application/zip",
    }:
        return True
    return parser_meta.get("extension") in {"7z", "gz", "rar", "tar", "tgz", "zip"}


def is_text_file(mime_type: str, parser_meta: dict) -> bool:
    if mime_type.startswith("text/"):
        return True
    return parser_meta.get("extension") in {
        "adoc",
        "cfg",
        "conf",
        "config",
        "css",
        "env",
        "ini",
        "log",
        "md",
        "properties",
        "rst",
        "text",
        "toml",
        "txt",
        "yaml",
        "yml",
    }


def read_blob_prefix(*, bucket: Bucket, bucket_key: str) -> bytes:
    if META_EXTRACT_PREFIX_BYTES <= 0:
        return b""
    response = object_service.fetch_blob_bytes(
        bucket=bucket,
        bucket_key=bucket_key,
        range_header=f"bytes=0-{META_EXTRACT_PREFIX_BYTES - 1}",
    )
    return response["Body"].read(META_EXTRACT_PREFIX_BYTES)


def read_blob_bytes_capped(
    *,
    bucket: Bucket,
    bucket_key: str,
    size_bytes: int,
    max_bytes: int,
) -> bytes:
    if max_bytes <= 0 or size_bytes <= 0:
        return b""
    byte_count = min(size_bytes, max_bytes)
    response = object_service.fetch_blob_bytes(
        bucket=bucket,
        bucket_key=bucket_key,
        range_header=f"bytes=0-{byte_count - 1}",
    )
    return response["Body"].read(byte_count)


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
