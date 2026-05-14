"""Archive metadata processor (ZIP/TAR/GZIP)."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.archive_meta.parser import parse_archive
from processors.type_meta import TypeMetaProcessor


class ArchiveMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArchiveMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "archive_meta"
    display_name: ClassVar[str] = "Archive metadata"
    description: ClassVar[str] = (
        "Lists entry counts and notable filenames inside archive files."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:archive_meta"
    default_concurrency: ClassVar[int] = 4
    max_concurrency: ClassVar[int] = 16

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "application/gzip",
        "application/x-gzip",
        "application/x-tar",
        "application/zip",
    )
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "application/gzip",
        "application/x-gzip",
        "application/x-tar",
        "application/zip",
    )
    default_extensions: ClassVar[tuple[str, ...]] = ()
    valid_extensions: ClassVar[tuple[str, ...]] = (
        "gz",
        "tar",
        "tar.gz",
        "tgz",
        "zip",
    )

    config_model: ClassVar[type[BaseModel]] = ArchiveMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.ARCHIVE_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_archive(content=content, file_info=file_info)


__all__ = ["ArchiveMetaConfig", "ArchiveMetaProcessor"]
