"""File search types and pure matching logic."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Iterable

from constants import SEARCH_SUPPORTED_KVS_OPS
from domain.exceptions import BadRequestError
from infra.db.models import File


@dataclass(frozen=True)
class KvsFilter:
    key: str
    op: str
    value: str

    @classmethod
    def parse(cls, raw: str) -> "KvsFilter":
        parts = raw.split(":", 2)
        if len(parts) != 3:
            raise BadRequestError(
                "kv filter must be '<key>:<op>:<value>' (e.g. row_count:gte:1000)"
            )
        key, op, value = (part.strip() for part in parts)
        if not key:
            raise BadRequestError("kv filter key cannot be empty")
        if op not in SEARCH_SUPPORTED_KVS_OPS:
            raise BadRequestError(
                f"kv filter op must be one of {sorted(SEARCH_SUPPORTED_KVS_OPS)}"
            )
        return cls(key=key, op=op, value=value)


@dataclass(frozen=True)
class SearchQuery:
    q: str | None = None
    tags: tuple[str, ...] = ()
    require_all_tags: bool = False
    keywords: tuple[str, ...] = ()
    mimetypes: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()
    min_size: int | None = None
    max_size: int | None = None
    actor_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    recursive: bool = False
    created_after: dt.datetime | None = None
    created_before: dt.datetime | None = None
    kvs: tuple[KvsFilter, ...] = ()
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

    file_tags = {_normalize(value) for value in meta.get("tags", []) if _normalize(value)}
    if query.tags:
        wanted = {_normalize(tag) for tag in query.tags if _normalize(tag)}
        if wanted:
            if query.require_all_tags:
                if not wanted <= file_tags:
                    return False
            elif not (wanted & file_tags):
                return False

    file_keywords = {
        _normalize(value) for value in meta.get("keywords", []) if _normalize(value)
    }
    if query.keywords:
        wanted = {_normalize(keyword) for keyword in query.keywords if _normalize(keyword)}
        if wanted and not (wanted & file_keywords):
            return False

    if query.q:
        haystack = " ".join(
            value
            for value in (
                file.name or "",
                meta.get("summary") or "",
                *(str(item) for item in meta.get("keywords", [])),
                *(str(item) for item in meta.get("tags", [])),
            )
            if value
        ).lower()
        for term in _tokenize(query.q):
            if term not in haystack:
                return False

    if query.kvs:
        kvs = meta.get("kvs") or {}
        for kvs_filter in query.kvs:
            if not _kvs_filter_matches(kvs, kvs_filter):
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


def count_list_axis(files: Iterable[File], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in files:
        meta = file.meta or {}
        for raw in meta.get(key, []) or ():
            value = _string_or_none(raw)
            if value is None:
                continue
            counts[value] = counts.get(value, 0) + 1
    return counts


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


def count_kvs_keys(files: Iterable[File]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in files:
        meta = file.meta or {}
        kvs = meta.get("kvs") or {}
        if not isinstance(kvs, dict):
            continue
        for raw_key in kvs.keys():
            key = _string_or_none(raw_key)
            if key is None:
                continue
            counts[key] = counts.get(key, 0) + 1
    return counts


def top_facet_values(counts: dict[str, int], top: int) -> list[FacetValue]:
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return [FacetValue(value=value, count=count) for value, count in items[:top]]


def _kvs_filter_matches(kvs: dict, kvs_filter: KvsFilter) -> bool:
    if kvs_filter.key not in kvs:
        return False
    actual = kvs[kvs_filter.key]

    if kvs_filter.op in {"gte", "lte", "lt", "gt"}:
        try:
            actual_num = float(actual)
            target_num = float(kvs_filter.value)
        except (TypeError, ValueError):
            return False
        if kvs_filter.op == "gte":
            return actual_num >= target_num
        if kvs_filter.op == "lte":
            return actual_num <= target_num
        if kvs_filter.op == "lt":
            return actual_num < target_num
        if kvs_filter.op == "gt":
            return actual_num > target_num

    if kvs_filter.op == "eq":
        return _coerce_str(actual) == kvs_filter.value
    if kvs_filter.op == "neq":
        return _coerce_str(actual) != kvs_filter.value
    return False


def _coerce_str(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


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
