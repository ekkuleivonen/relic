"""Postgres search store — JSONB containment + portable fallbacks."""

import uuid

from domain.files.search import SearchQuery, matches_text_filters, sort_key
from infra.db.models import Blob, File
from infra.db.repositories.search_portable import (
    SqlAlchemySearchStorePortable,
    _order_by,
)
from ports.repositories.search import SearchPage
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, selectinload


class SqlAlchemySearchStorePostgres(SqlAlchemySearchStorePortable):
    def search_page(
        self, *, scope_folder_ids: set[uuid.UUID], query: SearchQuery
    ) -> SearchPage:
        if not scope_folder_ids:
            return SearchPage(items=[], total=0)

        if query.kvs:
            matched = self.match_files(scope_folder_ids=scope_folder_ids, query=query)
            matched.sort(key=sort_key(query.sort), reverse=query.order == "desc")
            return SearchPage(
                items=matched[query.offset : query.offset + query.limit],
                total=len(matched),
            )

        base = _postgres_base_stmt(scope_folder_ids=scope_folder_ids, query=query)
        total = int(
            self._session.scalar(select(func.count()).select_from(base.subquery())) or 0
        )
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

        stmt = _postgres_base_stmt(
            scope_folder_ids=scope_folder_ids, query=query
        ).options(selectinload(File.blob))

        files = list(self._session.scalars(stmt).unique().all())
        if not query.kvs:
            return files

        return [file for file in files if matches_text_filters(file, query)]


def _postgres_base_stmt(*, scope_folder_ids: set[uuid.UUID], query: SearchQuery):
    meta = cast(File.meta, JSONB)
    stmt = select(File).where(File.folder_id.in_(scope_folder_ids))
    if query.actor_id is not None:
        stmt = stmt.where(File.actor_id == query.actor_id)
    if query.created_after is not None:
        stmt = stmt.where(File.created_at >= query.created_after)
    if query.created_before is not None:
        stmt = stmt.where(File.created_at < query.created_before)

    needs_blob_join = bool(
        query.mimetypes
        or query.extensions
        or query.min_size is not None
        or query.max_size is not None
        or query.sort == "size"
    )
    if needs_blob_join:
        stmt = stmt.join(Blob, File.blob_id == Blob.id)
        if query.mimetypes:
            stmt = stmt.where(Blob.mimetype.in_(query.mimetypes))
        if query.extensions:
            stmt = stmt.where(Blob.extension.in_(query.extensions))
        if query.min_size is not None:
            stmt = stmt.where(Blob.size_bytes >= query.min_size)
        if query.max_size is not None:
            stmt = stmt.where(Blob.size_bytes <= query.max_size)

    if query.tags:
        normalized = [tag.strip().lower() for tag in query.tags if tag.strip()]
        if query.require_all_tags:
            for tag in normalized:
                stmt = stmt.where(meta["tags"].contains([tag]))
        else:
            tag_clauses = [meta["tags"].contains([tag]) for tag in normalized]
            if tag_clauses:
                stmt = stmt.where(or_(*tag_clauses))

    if query.keywords:
        keyword_clauses = [
            meta["keywords"].contains([keyword.strip()])
            for keyword in query.keywords
            if keyword.strip()
        ]
        if keyword_clauses:
            stmt = stmt.where(or_(*keyword_clauses))

    if query.q:
        for term in query.q.split():
            cleaned = term.strip()
            if not cleaned:
                continue
            pattern = f"%{cleaned}%"
            stmt = stmt.where(
                or_(
                    File.name.ilike(pattern),
                    meta["summary"].as_string().ilike(pattern),
                    cast(meta["tags"], String).ilike(pattern),
                    cast(meta["keywords"], String).ilike(pattern),
                )
            )

    return stmt


def build_postgres_search_store(session: Session):
    return SqlAlchemySearchStorePostgres(session)
