"""Search and facet use cases."""

from __future__ import annotations

from dataclasses import dataclass, replace

from constants import (
    SEARCH_DEFAULT_FACET_TOP,
    SEARCH_MAX_FACET_TOP,
    SEARCH_MAX_LIMIT,
    SEARCH_SUPPORTED_ORDERS,
    SEARCH_SUPPORTED_SORT_FIELDS,
)
from domain.exceptions import BadRequestError
from domain.files.search import (
    FacetValue,
    KvsFilter,
    SearchQuery,
    count_kvs_keys,
    count_list_axis,
    count_scalar_axis,
    sort_key,
    top_facet_values,
)
from infra.db.models import File, User
from infra.db.stores.search_scope import scope_folder_ids
from application.uow import UnitOfWork


@dataclass(frozen=True)
class SearchResults:
    items: list[File]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class Facets:
    tags: list[FacetValue]
    mimetypes: list[FacetValue]
    extensions: list[FacetValue]
    kvs_keys: list[FacetValue]
    total: int


def search_files(uow: UnitOfWork, *, user: User, query: SearchQuery) -> SearchResults:
    _validate_query(query)
    matched = _matched_files(uow, user=user, query=query)
    matched.sort(key=sort_key(query.sort), reverse=query.order == "desc")
    page = matched[query.offset : query.offset + query.limit]
    return SearchResults(
        items=page,
        total=len(matched),
        limit=query.limit,
        offset=query.offset,
    )


def compute_facets(
    uow: UnitOfWork,
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

    full_match = _matched_files(uow, user=user, query=query)
    tags_axis = _matched_files(
        uow, user=user, query=replace(query, tags=(), require_all_tags=False)
    )
    mimetypes_axis = _matched_files(
        uow, user=user, query=replace(query, mimetypes=())
    )
    extensions_axis = _matched_files(
        uow, user=user, query=replace(query, extensions=())
    )
    kvs_axis = _matched_files(uow, user=user, query=replace(query, kvs=()))

    return Facets(
        tags=top_facet_values(count_list_axis(tags_axis, "tags"), top),
        mimetypes=top_facet_values(count_scalar_axis(mimetypes_axis, "mimetype"), top),
        extensions=top_facet_values(count_scalar_axis(extensions_axis, "extension"), top),
        kvs_keys=top_facet_values(count_kvs_keys(kvs_axis), top),
        total=len(full_match),
    )


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


def _matched_files(uow: UnitOfWork, *, user: User, query: SearchQuery) -> list[File]:
    scope_ids = scope_folder_ids(uow.session, user=user, query=query)
    return uow.search.match_files(scope_folder_ids=scope_ids, query=query)
