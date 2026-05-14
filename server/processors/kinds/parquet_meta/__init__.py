"""Parquet metadata processor."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.parquet_meta.parser import parse_parquet
from processors.type_meta import TypeMetaProcessor


class ParquetMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParquetMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "parquet_meta"
    display_name: ClassVar[str] = "Parquet metadata"
    description: ClassVar[str] = (
        "Inspects Parquet schema, row counts and partition layout for "
        "tabular discovery."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:parquet_meta"
    default_concurrency: ClassVar[int] = 4
    max_concurrency: ClassVar[int] = 16

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "application/vnd.apache.parquet",
    )
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "application/vnd.apache.parquet",
    )
    default_extensions: ClassVar[tuple[str, ...]] = ("parquet",)
    valid_extensions: ClassVar[tuple[str, ...]] = ("parquet",)

    config_model: ClassVar[type[BaseModel]] = ParquetMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.PARQUET_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_parquet(content=content, file_info=file_info)


__all__ = ["ParquetMetaConfig", "ParquetMetaProcessor"]
