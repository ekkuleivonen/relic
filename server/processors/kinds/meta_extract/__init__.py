"""Reference processor kind for file metadata extraction."""

from __future__ import annotations

import uuid
from typing import ClassVar

from domain.exceptions import ResourceNotFound
from pydantic import BaseModel, ConfigDict
from utils.logging import get_logger

from processors.base import (
    BaseProcessor,
    EnqueueContext,
    OrderingSemantics,
    ProcessorResult,
    ProcessorTask,
    RunContext,
)
from processors.kinds.meta_extract.extractor import (
    extract_file_metadata,
    require_file,
)

log = get_logger(__name__)


class MetaExtractConfig(BaseModel):
    """Configuration for metadata extraction.

    The current extractor is intentionally configured through environment byte
    caps rather than per-row options. Keeping this explicit empty schema makes
    invalid config fail fast and documents that no hidden knobs exist.
    """

    model_config = ConfigDict(extra="forbid")


class MetaExtractProcessor(BaseProcessor):
    kind: ClassVar[str] = "meta_extract"
    display_name: ClassVar[str] = "Metadata extraction"
    description: ClassVar[str] = (
        "Derives compact searchable metadata from file names and blob contents."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:meta_extract"
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
    config_model: ClassVar[type[BaseModel]] = MetaExtractConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    def should_enqueue(self, ctx: EnqueueContext) -> bool:
        if ctx.event.file_id is not None:
            return True
        log.info(
            "meta_extract_skipped_no_file_id",
            processor=ctx.processor.name,
            event_id=str(ctx.event.id),
            event_type=ctx.event.event_type,
        )
        return False

    def build_task(self, ctx: EnqueueContext) -> ProcessorTask:
        if ctx.event.file_id is None:
            raise ValueError("meta_extract task requires event.file_id")
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
        raw_blob_id = ctx.task.payload.get("blob_id")
        expected_blob_id = uuid.UUID(str(raw_blob_id)) if raw_blob_id else None
        try:
            result = extract_file_metadata(
                ctx.db,
                file_id=uuid.UUID(str(ctx.task.subject_id)),
                expected_blob_id=expected_blob_id,
            )
        except ResourceNotFound:
            log.info(
                "meta_extract_skipped_resource_missing",
                processor=ctx.processor.name,
                event_id=str(ctx.event.id),
                file_id=str(ctx.task.subject_id),
                event_type=ctx.event.event_type,
            )
            return ProcessorResult.skipped("source file, blob, or bucket is gone")

        if result.status == "stale":
            return ProcessorResult.stale(result.message or "metadata task is stale")
        return ProcessorResult.succeeded(file_id=str(ctx.task.subject_id))
