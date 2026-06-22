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
    SearchQuery,
    count_meta_keys,
    count_scalar_axis,
    top_facet_values,
)
from ports.entities import File, User
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
    meta_keys: list[FacetValue]
    mimetypes: list[FacetValue]
    extensions: list[FacetValue]
    total: int


def search_files(uow: UnitOfWork, *, user: User, query: SearchQuery) -> SearchResults:
    _validate_query(query)
    scope_ids = scope_folder_ids(uow.session, user=user, query=query)
    page = uow.search.search_page(scope_folder_ids=scope_ids, query=query)
    return SearchResults(
        items=page.items,
        total=page.total,
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
    meta_axis = _matched_files(uow, user=user, query=replace(query, meta=()))
    mimetypes_axis = _matched_files(
        uow, user=user, query=replace(query, mimetypes=())
    )
    extensions_axis = _matched_files(
        uow, user=user, query=replace(query, extensions=())
    )

    return Facets(
        meta_keys=top_facet_values(count_meta_keys(meta_axis), top),
        mimetypes=top_facet_values(count_scalar_axis(mimetypes_axis, "mimetype"), top),
        extensions=top_facet_values(count_scalar_axis(extensions_axis, "extension"), top),
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
