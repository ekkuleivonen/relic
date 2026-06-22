"""File search types and pure matching logic."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from constants import SEARCH_SUPPORTED_META_OPS
from domain.exceptions import BadRequestError
from infra.db.models import File

_MISSING = object()


@dataclass(frozen=True)
class MetaFilter:
    key: str
    op: str
    value: str

    @classmethod
    def parse(cls, raw: str) -> "MetaFilter":
        parts = raw.split(":", 2)
        if len(parts) != 3:
            raise BadRequestError(
                "meta filter must be '<key>:<op>:<value>' (e.g. row_count:gte:1000)"
            )
        key, op, value = (part.strip() for part in parts)
        if not key:
            raise BadRequestError("meta filter key cannot be empty")
        if op not in SEARCH_SUPPORTED_META_OPS:
            raise BadRequestError(
                f"meta filter op must be one of {sorted(SEARCH_SUPPORTED_META_OPS)}"
            )
        return cls(key=key, op=op, value=value)


@dataclass(frozen=True)
class SearchQuery:
    q: str | None = None
    mimetypes: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()
    min_size: int | None = None
    max_size: int | None = None
    actor_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    recursive: bool = False
    created_after: dt.datetime | None = None
    created_before: dt.datetime | None = None
    meta: tuple[MetaFilter, ...] = ()
    sort: str = "updated_at"
    order: str = "desc"
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class FacetValue:
    value: str
    count: int


def matches_blob_pre_filters(file: File, query: SearchQuery) -> bool:
    blob = file.blob
    if blob is None:
        return False
    if query.mimetypes and blob.mimetype not in query.mimetypes:
        return False
    if query.extensions and blob.extension not in query.extensions:
        return False
    if query.min_size is not None and blob.size_bytes < query.min_size:
        return False
    if query.max_size is not None and blob.size_bytes > query.max_size:
        return False
    return True


def matches_text_filters(file: File, query: SearchQuery) -> bool:
    meta = file.meta or {}

    if query.q:
        haystack = " ".join(
            [file.name or "", *flatten_meta_strings(meta)]
        ).lower()
        for term in _tokenize(query.q):
            if term not in haystack:
                return False

    for meta_filter in query.meta:
        if not _meta_filter_matches(meta, meta_filter):
            return False

    return True


def sort_key(field: str):
    if field == "name":
        return lambda file: (file.name or "").lower()
    if field == "size":
        return lambda file: _safe_size(file)
    if field == "created_at":
        return lambda file: file.created_at
    return lambda file: file.updated_at


def count_scalar_axis(files: Iterable[File], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in files:
        if file.blob is None:
            continue
        if key == "mimetype":
            value = _string_or_none(file.blob.mimetype)
        elif key == "extension":
            value = _string_or_none(file.blob.extension)
        else:
            value = _string_or_none((file.meta or {}).get(key))
        if value is None:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def count_meta_keys(files: Iterable[File]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in files:
        meta = file.meta or {}
        if not isinstance(meta, dict):
            continue
        for raw_key in meta.keys():
            key = _string_or_none(raw_key)
            if key is None:
                continue
            counts[key] = counts.get(key, 0) + 1
    return counts


def top_facet_values(counts: dict[str, int], top: int) -> list[FacetValue]:
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return [FacetValue(value=value, count=count) for value, count in items[:top]]


def flatten_meta_strings(meta: dict[str, Any], prefix: str = "") -> list[str]:
    strings: list[str] = []
    for raw_key, value in meta.items():
        key = _string_or_none(raw_key)
        if key is None:
            continue
        path = f"{prefix}.{key}" if prefix else key
        strings.extend(_flatten_value_strings(value, path))
    return strings


def get_meta_value(meta: dict[str, Any], path: str) -> Any:
    current: Any = meta
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _flatten_value_strings(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        return flatten_meta_strings(value, path)
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                out.extend(flatten_meta_strings(item, path))
            elif item is not None:
                out.append(str(item))
        return out
    return [str(value)]


def _meta_filter_matches(meta: dict[str, Any], meta_filter: MetaFilter) -> bool:
    actual = get_meta_value(meta, meta_filter.key)
    if actual is _MISSING:
        return False

    if isinstance(actual, list):
        return any(
            _scalar_meta_filter_matches(item, meta_filter) for item in actual
        )

    return _scalar_meta_filter_matches(actual, meta_filter)


def _scalar_meta_filter_matches(actual: Any, meta_filter: MetaFilter) -> bool:
    if meta_filter.op in {"gte", "lte", "lt", "gt"}:
        try:
            actual_num = float(actual)
            target_num = float(meta_filter.value)
        except (TypeError, ValueError):
            return False
        if meta_filter.op == "gte":
            return actual_num >= target_num
        if meta_filter.op == "lte":
            return actual_num <= target_num
        if meta_filter.op == "lt":
            return actual_num < target_num
        if meta_filter.op == "gt":
            return actual_num > target_num

    if meta_filter.op == "eq":
        return _coerce_str(actual) == meta_filter.value
    if meta_filter.op == "neq":
        return _coerce_str(actual) != meta_filter.value
    return False


def _coerce_str(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _tokenize(q: str) -> list[str]:
    return [token.lower() for token in q.split() if token]


def _safe_size(file: File) -> float:
    if file.blob is None:
        return 0
    return float(file.blob.size_bytes)


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
