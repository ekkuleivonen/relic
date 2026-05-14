"""Shared helpers for type-specific metadata processor kinds.

Every type-specific processor (image_meta, html_meta, ...) follows the same
pattern: subscribe to ``processor.file_info.completed``, fetch the file's
blob bytes (capped per kind), call its parser, and write a section.

This module factors out the boilerplate so each kind only needs to declare
its filters and supply the parser callable.
"""

from __future__ import annotations

import datetime as dt
import uuid
from abc import abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from domain.exceptions import ResourceNotFound
from domain.files.meta import FileMetaSection, apply_section, build_section_payload
from models import Blob, Bucket, File
from processors.base import (
    BaseProcessor,
    EnqueueContext,
    ProcessorResult,
    ProcessorTask,
    RunContext,
)
from services import objects as object_service
from utils.logging import get_logger

log = get_logger(__name__)


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


def write_section_result(
    db: Session,
    *,
    file: File,
    kind: str,
    section: FileMetaSection,
    base_overrides: dict[str, Any] | None = None,
) -> File:
    file.meta = apply_section(
        dict(file.meta),
        kind=kind,
        section=section,
        base_overrides=base_overrides,
    )
    db.flush()
    return file


def _file_info_section(meta: dict | None) -> dict:
    sections = (meta or {}).get("sections") or {}
    return sections.get("file_info") or {}


def file_info_kvs(file: File) -> dict[str, Any]:
    """Return the file_info section's kvs, defaulting to top-level fields."""
    section = _file_info_section(file.meta)
    if section.get("status") == "completed":
        return dict(section.get("kvs") or {})
    return {
        "size": (file.meta or {}).get("size"),
        "extension": (file.meta or {}).get("extension"),
        "mimetype": (file.meta or {}).get("mimetype"),
    }


# ---------------------------------------------------------------------------
# Base for type-specific metadata processors
# ---------------------------------------------------------------------------


class TypeMetaProcessor(BaseProcessor):
    """Base for type-specific metadata processors (image_meta, html_meta, ...).

    Subclasses set ``kind``, ``display_name``, ``default_task_queue``,
    ``valid_extensions``/``default_extensions``,
    ``valid_mimetype_prefixes``/``default_mimetype_prefixes``,
    ``max_bytes``, and override ``parser`` to return a section payload from
    the captured prefix bytes.
    """

    default_subscribed_event_types: tuple[str, ...] = (
        "processor.file_info.completed",
    )
    valid_event_types: tuple[str, ...] = (
        "processor.file_info.completed",
    )

    # Per-kind byte cap when reading blob bytes. Subclasses should override.
    max_bytes: int = 0

    @abstractmethod
    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Return ``{tags, keywords, summary, kvs}`` for the captured bytes."""

    # ---- Lifecycle ----

    def should_enqueue(self, ctx: EnqueueContext) -> bool:
        if ctx.event.file_id is None:
            return False
        try:
            file = require_file(ctx.db, ctx.event.file_id)
        except ResourceNotFound:
            return False
        info = _file_info_section(file.meta)
        if info.get("status") != "completed":
            log.info(
                "type_meta_skipped_file_info_pending",
                processor=ctx.processor.name,
                kind=self.kind,
                file_id=str(file.id),
            )
            return False
        kvs = info.get("kvs") or {}
        if not self.matches_filters(
            mimetype=kvs.get("mimetype"),
            extension=kvs.get("extension"),
            processor=ctx.processor,
        ):
            return False
        return True

    def build_task(self, ctx: EnqueueContext) -> ProcessorTask:
        if ctx.event.file_id is None:
            raise ValueError(f"{self.kind} task requires event.file_id")
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
                    "file blob changed before metadata extraction started"
                )
            blob = require_blob(ctx.db, file.blob_id)
            bucket = require_bucket(ctx.db, blob.bucket_id)
        except ResourceNotFound:
            log.info(
                "type_meta_skipped_resource_missing",
                processor=ctx.processor.name,
                kind=self.kind,
                file_id=str(file_id),
            )
            return ProcessorResult.skipped(
                "source file, blob, or bucket is gone"
            )

        info_kvs = file_info_kvs(file)
        if not self.matches_filters(
            mimetype=info_kvs.get("mimetype"),
            extension=info_kvs.get("extension"),
            processor=ctx.processor,
        ):
            return ProcessorResult.skipped(
                "file mimetype/extension does not match processor filters"
            )

        try:
            content = read_blob_bytes_capped(
                bucket=bucket,
                bucket_key=blob.bucket_key,
                size_bytes=blob.size_bytes,
                max_bytes=self.max_bytes,
            )
            if len(content) < blob.size_bytes:
                log.info(
                    f"{self.kind}_truncated",
                    file_id=str(file.id),
                    read_bytes=len(content),
                    blob_size=blob.size_bytes,
                    max_bytes=self.max_bytes,
                )
            payload = self.parse_bytes(content=content, file_info=info_kvs)
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

        if expected_blob_id is not None and file.blob_id != expected_blob_id:
            return ProcessorResult.stale(
                "file blob changed before metadata extraction finished"
            )

        section = build_section_payload(
            status="completed",
            extracted_at=dt.datetime.now(dt.UTC),
            tags=payload.get("tags") or [],
            keywords=payload.get("keywords") or [],
            summary=payload.get("summary"),
            kvs=payload.get("kvs") or {},
        )
        write_section_result(
            ctx.db,
            file=file,
            kind=self.kind,
            section=section,
        )
        return ProcessorResult.succeeded(file_id=str(file.id))


__all__ = [
    "TypeMetaProcessor",
    "file_info_kvs",
    "read_blob_bytes_capped",
    "require_blob",
    "require_bucket",
    "require_file",
    "write_section_result",
]
