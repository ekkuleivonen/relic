"""Seed processor that owns the base ``file_info`` section in file meta.

Reads a small prefix of the file's bytes, detects the mimetype via signature
and falls back to the filename, and writes the canonical
``meta.sections.file_info`` slot. Every type-specific metadata processor
(image_meta, html_meta, ...) waits for ``processor.file_info.completed`` so
they can read the authoritative mimetype and extension out of this section.
"""

from __future__ import annotations

import datetime as dt
import mimetypes
import uuid
from pathlib import PurePosixPath
from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from constants import FILE_INFO_PREFIX_BYTES
from domain.exceptions import ResourceNotFound
from domain.files.meta import build_section_payload
from models import Blob, Bucket
from processors.base import (
    BaseProcessor,
    EnqueueContext,
    OrderingSemantics,
    ProcessorResult,
    ProcessorTask,
    RunContext,
)
from processors.type_meta import (
    require_blob,
    require_bucket,
    require_file,
    write_section_result,
)
from services import objects as object_service
from utils.logging import get_logger

log = get_logger(__name__)


class FileInfoConfig(BaseModel):
    """Configuration for the file_info processor."""

    model_config = ConfigDict(extra="forbid")


class FileInfoProcessor(BaseProcessor):
    kind: ClassVar[str] = "file_info"
    display_name: ClassVar[str] = "File info"
    description: ClassVar[str] = (
        "Detects mimetype, extension and size; owns the canonical file_info "
        "section that every type-specific metadata processor depends on."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:file_info"
    default_concurrency: ClassVar[int] = 16
    max_concurrency: ClassVar[int] = 64

    default_subscribed_event_types: ClassVar[tuple[str, ...]] = (
        "file.created",
        "file.updated",
        "file.copied",
        "file.renamed",
    )
    valid_event_types: ClassVar[tuple[str, ...]] = (
        "file.created",
        "file.updated",
        "file.copied",
        "file.renamed",
    )

    config_model: ClassVar[type[BaseModel]] = FileInfoConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    def should_enqueue(self, ctx: EnqueueContext) -> bool:
        if ctx.event.file_id is None:
            return False
        return True

    def build_task(self, ctx: EnqueueContext) -> ProcessorTask:
        if ctx.event.file_id is None:
            raise ValueError("file_info task requires event.file_id")
        try:
            file = require_file(ctx.db, ctx.event.file_id)
        except ResourceNotFound:
            file = None
        blob_id = str(file.blob_id) if file is not None else None
        folder_id = file.folder_id if file is not None else ctx.event.folder_id
        input_version = blob_id or ctx.event.offset
        return ProcessorTask(
            processor_id=ctx.processor.id,
            processor_name=ctx.processor.name,
            processor_kind=self.kind,
            source_event_id=ctx.event.id,
            source_event_type=ctx.event.event_type,
            subject_type="file",
            subject_id=ctx.event.file_id,
            input_version=input_version,
            dedupe_key=f"{self.kind}:file:{ctx.event.file_id}:input:{input_version}",
            queue_name=self.default_task_queue,
            payload={
                "file_id": str(ctx.event.file_id),
                "blob_id": blob_id,
                "folder_id": str(folder_id) if folder_id is not None else None,
                "reason": ctx.event.event_type,
            },
        )

    def handle(self, ctx: RunContext) -> ProcessorResult:
        file_id = uuid.UUID(str(ctx.task.subject_id))
        raw_blob_id = ctx.task.payload.get("blob_id")
        expected_blob_id = uuid.UUID(str(raw_blob_id)) if raw_blob_id else None
        try:
            file = require_file(ctx.db, file_id)
            if expected_blob_id is not None and file.blob_id != expected_blob_id:
                return ProcessorResult.stale(
                    "file blob changed before file_info started"
                )
            blob = require_blob(ctx.db, file.blob_id)
            bucket = require_bucket(ctx.db, blob.bucket_id)
        except ResourceNotFound:
            log.info(
                "file_info_skipped_resource_missing",
                processor=ctx.processor.name,
                file_id=str(file_id),
            )
            return ProcessorResult.skipped(
                "source file, blob, or bucket is gone"
            )

        try:
            prefix = read_blob_prefix(bucket=bucket, bucket_key=blob.bucket_key)
        except Exception as exc:
            section = build_section_payload(
                status="failed",
                extracted_at=dt.datetime.now(dt.UTC),
                error_class=type(exc).__name__,
                error_message=str(exc)[:1000],
            )
            write_section_result(
                ctx.db,
                file=file,
                kind=self.kind,
                section=section,
            )
            raise

        mimetype = detect_mime_type(prefix=prefix, filename=file.name)
        extension = (
            PurePosixPath(file.name).suffix.removeprefix(".").lower() or ""
        )
        size = blob.size_bytes

        if expected_blob_id is not None and file.blob_id != expected_blob_id:
            return ProcessorResult.stale(
                "file blob changed before file_info finished"
            )

        section = build_section_payload(
            status="completed",
            extracted_at=dt.datetime.now(dt.UTC),
            tags=_baseline_tags(mimetype=mimetype, extension=extension),
            keywords=[],
            summary=f"{mimetype} ({size} bytes)",
            kvs={
                "size": size,
                "extension": extension,
                "mimetype": mimetype,
                "original_filename": (file.meta or {}).get("original_filename")
                or file.name,
            },
        )
        write_section_result(
            ctx.db,
            file=file,
            kind=self.kind,
            section=section,
            base_overrides={
                "size": size,
                "extension": extension,
                "mimetype": mimetype,
            },
        )
        return ProcessorResult.succeeded(file_id=str(file.id))


# ---------------------------------------------------------------------------
# Mimetype detection
# ---------------------------------------------------------------------------


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


def read_blob_prefix(*, bucket: Bucket, bucket_key: str) -> bytes:
    if FILE_INFO_PREFIX_BYTES <= 0:
        return b""
    response = object_service.fetch_blob_bytes(
        bucket=bucket,
        bucket_key=bucket_key,
        range_header=f"bytes=0-{FILE_INFO_PREFIX_BYTES - 1}",
    )
    return response["Body"].read(FILE_INFO_PREFIX_BYTES)


def _baseline_tags(*, mimetype: str, extension: str) -> list[str]:
    tags: list[str] = []
    if mimetype.startswith("image/"):
        tags.append("image")
    elif mimetype.startswith("audio/"):
        tags.append("audio")
    elif mimetype.startswith("video/"):
        tags.append("video")
    elif mimetype.startswith("text/"):
        tags.append("text")
    elif mimetype == "application/pdf":
        tags.append("pdf")
    elif mimetype == "application/vnd.apache.parquet":
        tags.append("parquet")
    if extension:
        tags.append(extension)
    return tags


# Re-export for callers that test mimetype detection without going through
# the full processor pipeline.
__all__ = [
    "FileInfoConfig",
    "FileInfoProcessor",
    "detect_mime_type",
    "detect_signature_mime_type",
    "read_blob_prefix",
]


# Avoid unused-import warnings on Session/Blob; they're needed for type hints
# of helpers exposed for tests.
_ = Session
_ = Blob
