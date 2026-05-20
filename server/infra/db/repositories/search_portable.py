"""Portable search store — SQL pre-filters + Python JSON matching."""

import uuid

from domain.files.search import (
    SearchQuery,
    matches_blob_pre_filters,
    matches_text_filters,
)
from infra.db.models import Blob, File
from ports.repositories.search import SearchStore
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload


class SqlAlchemySearchStorePortable:
    def __init__(self, session: Session) -> None:
        self._session = session

    def match_files(
        self, *, scope_folder_ids: set[uuid.UUID], query: SearchQuery
    ) -> list[File]:
        if not scope_folder_ids:
            return []

        stmt = (
            select(File)
            .where(File.folder_id.in_(scope_folder_ids))
            .options(selectinload(File.blob))
        )
        if query.actor_id is not None:
            stmt = stmt.where(File.actor_id == query.actor_id)
        if query.created_after is not None:
            stmt = stmt.where(File.created_at >= query.created_after)
        if query.created_before is not None:
            stmt = stmt.where(File.created_at < query.created_before)

        if _has_blob_sql_filters(query):
            stmt = stmt.join(Blob, File.blob_id == Blob.id)
            if query.mimetypes:
                stmt = stmt.where(Blob.mimetype.in_(query.mimetypes))
            if query.extensions:
                stmt = stmt.where(Blob.extension.in_(query.extensions))
            if query.min_size is not None:
                stmt = stmt.where(Blob.size_bytes >= query.min_size)
            if query.max_size is not None:
                stmt = stmt.where(Blob.size_bytes <= query.max_size)

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


def build_portable_search_store(session: Session) -> SearchStore:
    return SqlAlchemySearchStorePortable(session)
