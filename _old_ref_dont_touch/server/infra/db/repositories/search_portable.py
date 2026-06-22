"""Portable search store — SQL pre-filters + Python JSON matching."""

import uuid

from domain.files.search import (
    SearchQuery,
    matches_blob_pre_filters,
    matches_text_filters,
    sort_key,
)
from infra.db.models import Blob, File
from ports.repositories.search import SearchPage, SearchStore
from sqlalchemy import asc, desc, func, nullslast, select
from sqlalchemy.orm import Session, selectinload


class SqlAlchemySearchStorePortable:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search_page(
        self, *, scope_folder_ids: set[uuid.UUID], query: SearchQuery
    ) -> SearchPage:
        if not scope_folder_ids:
            return SearchPage(items=[], total=0)

        if _requires_python_filtering(query):
            matched = self.match_files(scope_folder_ids=scope_folder_ids, query=query)
            matched.sort(key=sort_key(query.sort), reverse=query.order == "desc")
            return SearchPage(
                items=matched[query.offset : query.offset + query.limit],
                total=len(matched),
            )

        base = _base_stmt(scope_folder_ids=scope_folder_ids, query=query)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = int(self._session.scalar(count_stmt) or 0)
        page_stmt = (
            base.options(selectinload(File.blob))
            .order_by(*_order_by(query))
            .limit(query.limit)
            .offset(query.offset)
        )
        items = list(self._session.scalars(page_stmt).unique().all())
        return SearchPage(items=items, total=total)

    def match_files(
        self, *, scope_folder_ids: set[uuid.UUID], query: SearchQuery
    ) -> list[File]:
        if not scope_folder_ids:
            return []

        stmt = _base_stmt(scope_folder_ids=scope_folder_ids, query=query).options(
            selectinload(File.blob)
        )

        files = list(self._session.scalars(stmt).unique().all())
        return [
            file
            for file in files
            if matches_blob_pre_filters(file, query)
            and matches_text_filters(file, query)
        ]


def _has_blob_sql_filters(query: SearchQuery) -> bool:
    return bool(
        query.mimetypes
        or query.extensions
        or query.min_size is not None
        or query.max_size is not None
    )


def _requires_blob_join(query: SearchQuery) -> bool:
    return _has_blob_sql_filters(query) or query.sort == "size"


def _requires_python_filtering(query: SearchQuery) -> bool:
    return bool(query.q or query.meta)


def _base_stmt(*, scope_folder_ids: set[uuid.UUID], query: SearchQuery):
    stmt = select(File).where(File.folder_id.in_(scope_folder_ids))
    if query.actor_id is not None:
        stmt = stmt.where(File.actor_id == query.actor_id)
    if query.created_after is not None:
        stmt = stmt.where(File.created_at >= query.created_after)
    if query.created_before is not None:
        stmt = stmt.where(File.created_at < query.created_before)

    if _requires_blob_join(query):
        stmt = stmt.join(Blob, File.blob_id == Blob.id)
        if query.mimetypes:
            stmt = stmt.where(Blob.mimetype.in_(query.mimetypes))
        if query.extensions:
            stmt = stmt.where(Blob.extension.in_(query.extensions))
        if query.min_size is not None:
            stmt = stmt.where(Blob.size_bytes >= query.min_size)
        if query.max_size is not None:
            stmt = stmt.where(Blob.size_bytes <= query.max_size)

    return stmt


def _order_by(query: SearchQuery):
    order_asc = query.order == "asc"
    primary = asc if order_asc else desc
    tie = asc(File.id) if order_asc else desc(File.id)

    if query.sort == "name":
        return primary(File.name), tie
    if query.sort == "created_at":
        return primary(File.created_at), tie
    if query.sort == "size":
        return nullslast(primary(Blob.size_bytes)), tie
    return primary(File.updated_at), tie


def build_portable_search_store(session: Session) -> SearchStore:
    return SqlAlchemySearchStorePortable(session)
