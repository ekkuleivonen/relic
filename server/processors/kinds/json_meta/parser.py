"""JSON parser. Writes compact discovery metadata into file meta."""

from __future__ import annotations

import json as json_lib
import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import IO, Any

from domain.files.meta import build_parser_discovery, empty_parser_discovery
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_MAX_RECORDS_TO_SCAN = 100
_MAX_NESTED_KEYS = 20


def empty_json_meta() -> dict[str, Any]:
    return empty_parser_discovery(tags=["json", "data"])


def parse_json(
    *, content: bytes, file_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse JSON bytes into a discovery payload. Never raises."""
    try:
        return parse(content, file_info=file_info)
    except Exception as exc:
        log.warning("json_parse_failed", error=str(exc))
        return empty_json_meta()


def parse(
    content: bytes | IO[bytes], *, file_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse JSON or JSON Lines bytes into the common discovery payload."""
    full_bytes = content if isinstance(content, bytes) else content.read()
    text = _decode_json_text(full_bytes)

    try:
        data = json_lib.loads(text)
    except json_lib.JSONDecodeError:
        jsonl_records = _parse_jsonl(text)
        if jsonl_records is None:
            return _build_malformed()
        return _build_jsonl(jsonl_records, file_info=file_info)

    return _build_json(data, file_info=file_info)


def _build_json(data: Any, *, file_info: dict[str, Any] | None) -> dict[str, Any]:
    tags = ["json", "data"]
    keywords: list[str | None] = []
    kvs: dict[str, Any] = {}
    summary: str

    if isinstance(data, dict):
        tags.append("object")
        top_level_keys = list(data.keys())
        keywords.extend(_schema_keywords(top_level_keys))
        keywords.extend(_nested_object_keys(data.values()))
        summary = f"JSON object with {len(top_level_keys)} top-level keys"
    elif isinstance(data, list):
        tags.append("array")
        if _is_record_array(data):
            tags.append("records")
            record_keys = _record_keys(data)
            keywords.extend(_schema_keywords(record_keys))
            kvs["record_count"] = len(data)
            summary = f"JSON records with {len(data)} rows and {len(record_keys)} fields"
        else:
            kvs["record_count"] = len(data)
            summary = f"JSON array with {len(data)} items"
    else:
        tags.append("scalar")
        summary = "JSON scalar value"

    domain_hints = _domain_hints(file_info=file_info, keys=keywords, data=data)
    tags.extend(domain_hints)
    keywords.extend(domain_hints)

    return _shape(tags=tags, keywords=keywords, summary=summary, kvs=kvs)


def _build_jsonl(
    records: list[Any], *, file_info: dict[str, Any] | None
) -> dict[str, Any]:
    tags = ["json", "data", "jsonl"]
    keywords: list[str | None] = []

    if _is_record_array(records):
        tags.append("records")
        record_keys = _record_keys(records)
        keywords.extend(_schema_keywords(record_keys))
        summary = f"JSONL records with {len(records)} rows and {len(record_keys)} fields"
    else:
        record_keys = []
        summary = f"JSONL with {len(records)} records"

    domain_hints = _domain_hints(file_info=file_info, keys=keywords, data=records)
    tags.extend(domain_hints)
    keywords.extend(domain_hints)

    return _shape(
        tags=tags,
        keywords=keywords,
        summary=summary,
        kvs={"record_count": len(records)},
    )


def _build_malformed() -> dict[str, Any]:
    return _shape(
        tags=["json", "data", "malformed"],
        keywords=[],
        summary="malformed JSON document",
        kvs={},
    )


def _shape(
    *,
    tags: list[str | None],
    keywords: list[str | None],
    summary: str | None,
    kvs: dict[str, Any],
) -> dict[str, Any]:
    return build_parser_discovery(
        tags=_dedupe(tags, limit=12),
        keywords=_dedupe(keywords, limit=_MAX_KEYWORDS),
        summary=summary,
        kvs=kvs,
    )


def _decode_json_text(content: bytes) -> str:
    if not content:
        return ""
    for bom, encoding in (
        (b"\xff\xfe\x00\x00", "utf-32-le"),
        (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xff\xfe", "utf-16-le"),
        (b"\xfe\xff", "utf-16-be"),
        (b"\xef\xbb\xbf", "utf-8-sig"),
    ):
        if content.startswith(bom):
            return content.decode(encoding)
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="replace")


def _parse_jsonl(text: str) -> list[Any] | None:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return None

    records: list[Any] = []
    for line in lines:
        try:
            records.append(json_lib.loads(line))
        except json_lib.JSONDecodeError:
            return None
    return records


def _is_record_array(values: list[Any]) -> bool:
    return bool(values) and all(isinstance(value, dict) for value in values)


def _record_keys(records: list[Any]) -> list[str]:
    keys: list[str] = []
    for record in records[:_MAX_RECORDS_TO_SCAN]:
        if not isinstance(record, dict):
            continue
        keys.extend(str(key) for key in record)
    return _dedupe(keys, limit=_MAX_KEYWORDS)


def _schema_keywords(keys: Iterable[Any]) -> list[str | None]:
    return [_normalize_keyword(str(key)) for key in keys]


def _nested_object_keys(values: Iterable[Any]) -> list[str]:
    keys: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        keys.extend(str(key) for key in value)
        if len(keys) >= _MAX_NESTED_KEYS:
            break
    return _dedupe(keys, limit=_MAX_NESTED_KEYS)


def _domain_hints(
    *,
    file_info: dict[str, Any] | None,
    keys: Iterable[str | None],
    data: Any,
) -> list[str]:
    hints: list[str | None] = []
    filename = _original_filename(file_info)
    filename_words = set(_filename_words(filename))
    key_set = {_normalize_keyword(key) for key in keys}
    key_set.discard(None)

    lower_name = filename.lower()
    if lower_name.endswith("package.json"):
        hints.append("package")
    if "lock" in filename_words or lower_name.endswith(("-lock.json", ".lock.json")):
        hints.append("lockfile")
    if "config" in filename_words or any(word.endswith("config") for word in filename_words):
        hints.append("config")
    if "export" in filename_words:
        hints.append("export")
    if lower_name.endswith(".ipynb") or {"cells", "metadata", "nbformat"}.issubset(key_set):
        hints.append("notebook")
    if _looks_like_geojson(filename=filename, key_set=key_set, data=data):
        hints.append("geo")
    if {"openapi", "paths"}.issubset(key_set) or {"swagger", "paths"}.issubset(key_set):
        hints.append("api")

    return _dedupe(hints, limit=8)


def _looks_like_geojson(*, filename: str, key_set: set[str | None], data: Any) -> bool:
    if PurePosixPath(filename).suffix.lower() == ".geojson":
        return True
    if not isinstance(data, dict):
        return False
    json_type = data.get("type")
    return (
        isinstance(json_type, str)
        and json_type.lower() in {"featurecollection", "feature", "geometrycollection"}
        and bool({"features", "geometry", "coordinates"} & key_set)
    )


def _original_filename(file_info: dict[str, Any] | None) -> str:
    if not file_info:
        return ""
    value = file_info.get("original_filename")
    return str(value or "")


def _filename_words(filename: str) -> list[str]:
    return [
        word
        for word in re.split(r"[^a-zA-Z0-9]+", PurePosixPath(filename).name.lower())
        if word
    ]


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
