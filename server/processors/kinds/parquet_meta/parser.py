"""Parquet parser. Returns a discovery payload for the parquet_meta section."""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import IO, Any

import pyarrow.parquet as pq

from domain.files.meta import build_parser_discovery, empty_parser_discovery
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_WIDE_COLUMN_THRESHOLD = 50
_TALL_ROW_THRESHOLD = 10_000


def empty_parquet_meta() -> dict[str, Any]:
    return empty_parser_discovery(tags=["data", "dataset", "parquet"])


def parse_parquet(
    *, content: bytes, file_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse Parquet bytes into a discovery payload. Never raises."""
    if not content:
        return empty_parquet_meta()
    try:
        return parse(content, file_info=file_info)
    except Exception as exc:
        log.warning("parquet_parse_failed", error=str(exc))
        return empty_parquet_meta()


def parse(
    content: bytes | IO[bytes], *, file_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse Parquet bytes into the common discovery payload."""
    source = io.BytesIO(content) if isinstance(content, bytes) else content
    parquet_file = pq.ParquetFile(source)
    metadata = parquet_file.metadata
    schema = parquet_file.schema_arrow

    details = {
        "row_count": metadata.num_rows,
        "column_count": metadata.num_columns,
        "row_group_count": metadata.num_row_groups,
        "columns": [field.name for field in schema],
        "types": [_normalize_type(field.type) for field in schema],
        "compressions": _compressions(metadata),
        "partition_keys": _partition_keys(file_info),
    }
    return _build_discovery(details)


def _build_discovery(details: dict[str, Any]) -> dict[str, Any]:
    row_count = details["row_count"]
    column_count = details["column_count"]

    tags = ["data", "dataset", "parquet", "table", "columnar"]
    if column_count >= _WIDE_COLUMN_THRESHOLD:
        tags.append("wide")
    if row_count >= _TALL_ROW_THRESHOLD:
        tags.append("tall")
    if details["partition_keys"]:
        tags.append("partitioned")

    keywords = _dedupe(
        [
            *details["partition_keys"],
            *details["columns"],
            *details["types"],
            *details["compressions"],
        ],
        limit=_MAX_KEYWORDS,
    )

    return build_parser_discovery(
        tags=_dedupe(tags, limit=12),
        keywords=keywords,
        summary=_summary(row_count=row_count, column_count=column_count),
        kvs={"row_count": row_count, "column_count": column_count},
    )


def _compressions(metadata: Any) -> list[str]:
    values: list[str] = []
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            value = getattr(row_group.column(column_index), "compression", None)
            if value:
                values.append(str(value))
    return _dedupe(values, limit=8)


def _partition_keys(file_info: dict[str, Any] | None) -> list[str]:
    filename = _original_filename(file_info)
    parts = PurePosixPath(filename).parts
    keys: list[str] = []
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key and value:
            keys.append(key)
    return _dedupe(keys, limit=8)


def _normalize_type(value: Any) -> str | None:
    text = str(value).lower()
    if text.startswith("timestamp"):
        return "timestamp"
    if text.startswith("decimal"):
        return "decimal"
    if text.startswith("list"):
        return "list"
    if text.startswith("struct"):
        return "struct"
    return text or None


def _summary(*, row_count: int, column_count: int) -> str:
    return f"parquet table with {row_count} rows and {column_count} columns"


def _original_filename(file_info: dict[str, Any] | None) -> str:
    if not file_info:
        return ""
    return str(file_info.get("original_filename") or "")


def _dedupe(values: Iterable[str | None], *, limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize_keyword(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _normalize_keyword(value: Any) -> str | None:
    if value is None:
        return None
    keyword = re.sub(r"\s+", " ", str(value).strip().lower())
    return keyword or None
