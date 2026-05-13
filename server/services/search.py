"""File search and faceting over the canonical FileMeta schema.

The search engine is shaped around the four query primitives of `FileMeta`:

- ``tags``: low-cardinality controlled vocabulary, used for filtering and grouping
- ``keywords``: capped human-searchable terms, used for full-text-style match
- ``summary``: short description, also feeds the omnisearch term match
- ``kvs``: scalar facts, used for range/equality predicates

Plus the surrounding structured fields (``mimetype``, ``extension``, ``size``,
``original_filename``) and the columns on ``File`` itself (``folder_id``,
``actor_id``, ``created_at``).

The implementation does a SQL-side pre-filter on what is portable across SQLite
(tests) and Postgres (prod), then applies the JSON-shaped filters in Python.
At early product scale the matched candidate set is small enough that this is
fast; the JSONB indexes added in the alembic migration keep the SQL pre-filter
cheap as the corpus grows. When tag/keyword cardinality becomes a hotspot we
can move those predicates into native ``@>`` / ``?|`` Postgres expressions
behind the same service interface.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from constants import (
    SEARCH_DEFAULT_FACET_TOP,
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_FACET_TOP,
    SEARCH_MAX_LIMIT,
    SEARCH_SUPPORTED_KVS_OPS,
    SEARCH_SUPPORTED_ORDERS,
    SEARCH_SUPPORTED_SORT_FIELDS,
)
from domain.exceptions import BadRequestError
from models import File, User
from services import folder_access as folder_access_service
from services import filesystem as filesystem_service


@dataclass(frozen=True)
class KvsFilter:
    """A predicate over one ``meta.kvs`` key."""

    key: str
    op: str
    value: str

    @classmethod
    def parse(cls, raw: str) -> "KvsFilter":
        """Parse ``<key>:<op>:<value>`` (value may itself contain colons)."""
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
    limit: int = SEARCH_DEFAULT_LIMIT
    offset: int = 0


@dataclass(frozen=True)
class SearchResults:
    items: list[File]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class FacetValue:
    value: str
    count: int


@dataclass(frozen=True)
class Facets:
    """Facet counts. Each axis is computed against the result set
    with that axis's own filter cleared so the user can switch facet values
    without the panel collapsing to one entry.

    ``kvs_keys`` counts how many files in the matching result set carry
    each ``meta.kvs`` key. It powers the kvs filter editor's key picker so
    users see only keys that actually exist in their corpus."""

    tags: list[FacetValue]
    mimetypes: list[FacetValue]
    extensions: list[FacetValue]
    kvs_keys: list[FacetValue]
    total: int


def search_files(db: Session, *, user: User, query: SearchQuery) -> SearchResults:
    _validate_query(query)
    matched = _matched_files(db, user=user, query=query)
    matched.sort(key=_sort_key(query.sort), reverse=query.order == "desc")
    page = matched[query.offset : query.offset + query.limit]
    return SearchResults(
        items=page,
        total=len(matched),
        limit=query.limit,
        offset=query.offset,
    )


def compute_facets(
    db: Session,
    *,
    user: User,
    query: SearchQuery,
    top: int = SEARCH_DEFAULT_FACET_TOP,
) -> Facets:
    _validate_query(query)
    if top < 1:
        raise BadRequestError("facet top must be >= 1")
    if top > SEARCH_MAX_FACET_TOP:
        top = SEARCH_MAX_FACET_TOP

    full_match = _matched_files(db, user=user, query=query)

    tags_axis = _matched_files(
        db, user=user, query=replace(query, tags=(), require_all_tags=False)
    )
    mimetypes_axis = _matched_files(
        db, user=user, query=replace(query, mimetypes=())
    )
    extensions_axis = _matched_files(
        db, user=user, query=replace(query, extensions=())
    )
    kvs_axis = _matched_files(db, user=user, query=replace(query, kvs=()))

    return Facets(
        tags=_top_facets(_count_list(tags_axis, "tags"), top),
        mimetypes=_top_facets(_count_scalar(mimetypes_axis, "mimetype"), top),
        extensions=_top_facets(_count_scalar(extensions_axis, "extension"), top),
        kvs_keys=_top_facets(_count_kvs_keys(kvs_axis), top),
        total=len(full_match),
    )


# ---------------------------------------------------------------------------
# Internal: candidate selection + matching
# ---------------------------------------------------------------------------


def _validate_query(query: SearchQuery) -> None:
    if query.sort not in SEARCH_SUPPORTED_SORT_FIELDS:
        raise BadRequestError(
            f"sort must be one of {sorted(SEARCH_SUPPORTED_SORT_FIELDS)}"
        )
    if query.order not in SEARCH_SUPPORTED_ORDERS:
        raise BadRequestError("order must be 'asc' or 'desc'")
    if query.limit < 1:
        raise BadRequestError("limit must be >= 1")
    if query.limit > SEARCH_MAX_LIMIT:
        raise BadRequestError(f"limit must be <= {SEARCH_MAX_LIMIT}")
    if query.offset < 0:
        raise BadRequestError("offset must be >= 0")
    if query.min_size is not None and query.min_size < 0:
        raise BadRequestError("min_size must be >= 0")
    if query.max_size is not None and query.max_size < 0:
        raise BadRequestError("max_size must be >= 0")
    if (
        query.min_size is not None
        and query.max_size is not None
        and query.min_size > query.max_size
    ):
        raise BadRequestError("min_size cannot exceed max_size")


def _matched_files(db: Session, *, user: User, query: SearchQuery) -> list[File]:
    """Return all files (no pagination) that satisfy the query."""
    candidates = _candidates(db, user=user, query=query)
    return [file for file in candidates if _matches_text_filters(file, query)]


def _candidates(db: Session, *, user: User, query: SearchQuery) -> list[File]:
    """SQL-pre-filter pass: returns the candidate set after applying everything
    that maps cleanly to a portable WHERE clause."""
    visible_ids = folder_access_service.visible_folder_ids(db, user)
    if not visible_ids:
        return []

    scope_ids = _scope_folder_ids(db, query=query, visible_ids=visible_ids)
    if not scope_ids:
        return []

    stmt = select(File).where(File.folder_id.in_(scope_ids))
    if query.actor_id is not None:
        stmt = stmt.where(File.actor_id == query.actor_id)
    if query.created_after is not None:
        stmt = stmt.where(File.created_at >= query.created_after)
    if query.created_before is not None:
        stmt = stmt.where(File.created_at < query.created_before)

    files = list(db.scalars(stmt).all())
    return [file for file in files if _matches_meta_pre_filters(file, query)]


def _scope_folder_ids(
    db: Session,
    *,
    query: SearchQuery,
    visible_ids: set[uuid.UUID],
) -> set[uuid.UUID]:
    if query.folder_id is None:
        return visible_ids

    if query.recursive:
        descendants = filesystem_service.collect_descendant_folder_ids(
            db, query.folder_id
        )
        return {fid for fid in descendants if fid in visible_ids}

    if query.folder_id not in visible_ids:
        return set()
    return {query.folder_id}


def _matches_meta_pre_filters(file: File, query: SearchQuery) -> bool:
    """Predicates that are technically expressible in SQL but kept in Python
    so the search engine works identically on SQLite (tests) and Postgres
    (prod). The Postgres-side btree indexes on ``meta->>'mimetype'`` and
    ``meta->>'extension'`` keep these cheap once the candidate set is loaded."""
    meta = file.meta or {}

    if query.mimetypes:
        if (meta.get("mimetype") or "") not in query.mimetypes:
            return False

    if query.extensions:
        if (meta.get("extension") or "") not in query.extensions:
            return False

    if query.min_size is not None or query.max_size is not None:
        size = meta.get("size")
        if not isinstance(size, (int, float)):
            return False
        if query.min_size is not None and size < query.min_size:
            return False
        if query.max_size is not None and size > query.max_size:
            return False

    return True


def _matches_text_filters(file: File, query: SearchQuery) -> bool:
    meta = file.meta or {}

    file_tags = {_normalize(value) for value in meta.get("tags", []) if _normalize(value)}
    if query.tags:
        wanted = {_normalize(tag) for tag in query.tags if _normalize(tag)}
        if not wanted:
            pass
        elif query.require_all_tags:
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
                meta.get("original_filename") or "",
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


def _sort_key(field: str):
    if field == "name":
        return lambda file: (file.name or "").lower()
    if field == "size":
        return lambda file: _safe_size(file)
    if field == "created_at":
        return lambda file: file.created_at
    return lambda file: file.updated_at


def _safe_size(file: File) -> float:
    meta = file.meta or {}
    size = meta.get("size")
    return size if isinstance(size, (int, float)) else 0


# ---------------------------------------------------------------------------
# Internal: facet counting
# ---------------------------------------------------------------------------


def _count_list(files: Iterable[File], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in files:
        meta = file.meta or {}
        for raw in meta.get(key, []) or ():
            value = _string_or_none(raw)
            if value is None:
                continue
            counts[value] = counts.get(value, 0) + 1
    return counts


def _count_scalar(files: Iterable[File], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in files:
        meta = file.meta or {}
        value = _string_or_none(meta.get(key))
        if value is None:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _count_kvs_keys(files: Iterable[File]) -> dict[str, int]:
    """Count files that carry each `meta.kvs` key. A key is counted at most
    once per file regardless of value, since the editor cares about discovery,
    not value distribution."""
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


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _top_facets(counts: dict[str, int], top: int) -> list[FacetValue]:
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return [FacetValue(value=value, count=count) for value, count in items[:top]]
