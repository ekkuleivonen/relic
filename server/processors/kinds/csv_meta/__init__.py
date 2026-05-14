"""CSV metadata processor."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.csv_meta.parser import parse_csv
from processors.type_meta import TypeMetaProcessor


class CsvMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CsvMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "csv_meta"
    display_name: ClassVar[str] = "CSV metadata"
    description: ClassVar[str] = (
        "Detects delimiters, header rows, row/column counts and column types "
        "for CSV files."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:csv_meta"
    default_concurrency: ClassVar[int] = 4
    max_concurrency: ClassVar[int] = 16

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("text/csv",)
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "text/csv",
        "application/csv",
    )
    default_extensions: ClassVar[tuple[str, ...]] = ("csv",)
    valid_extensions: ClassVar[tuple[str, ...]] = ("csv", "tsv")

    config_model: ClassVar[type[BaseModel]] = CsvMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.CSV_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_csv(content=content)


__all__ = ["CsvMetaConfig", "CsvMetaProcessor"]
