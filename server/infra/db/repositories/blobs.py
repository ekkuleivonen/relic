import datetime as dt
import uuid

import settings as S
from domain.exceptions import ResourceNotFound
from infra.db.models import Blob, File
from ports.repositories.blobs import BlobStore
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload


class SqlAlchemyBlobStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, blob_id: uuid.UUID) -> Blob:
        blob = self._session.get(Blob, blob_id)
        if blob is None:
            raise ResourceNotFound("Blob not found")
        return blob

    def touch_access(
        self, blob: Blob, *, debounce_minutes: int | None = None
    ) -> bool:
        effective_now = dt.datetime.now(dt.UTC)
        effective_debounce = (
            debounce_minutes
            if debounce_minutes is not None
            else S.ACCESS_TOUCH_DEBOUNCE_MINUTES
        )

        last = blob.accessed_at
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=dt.UTC)
            if (effective_now - last) < dt.timedelta(minutes=effective_debounce):
                return False

        blob.accessed_at = effective_now
        self._session.flush()
        return True

    def list_dereferenced_for_purge(self, *, batch: int) -> list[Blob]:
        stmt = (
            select(Blob)
            .where(Blob.refcount < 1)
            .order_by(Blob.updated_at.asc(), Blob.created_at.asc())
            .limit(batch)
        )
        dialect = self._session.get_bind().dialect.name
        if dialect in ("postgresql", "sqlite"):
            stmt = stmt.with_for_update(skip_locked=True)
        return list(self._session.scalars(stmt))

    def delete_row(self, blob: Blob) -> None:
        self._session.delete(blob)

    def list_pressured_candidates(
        self, *, storage_backend_ids: set[uuid.UUID], limit: int
    ) -> list[Blob]:
        if not storage_backend_ids:
            return []
        return list(
            self._session.scalars(
                select(Blob)
                .where(Blob.storage_backend_id.in_(storage_backend_ids), Blob.refcount > 0)
                .options(selectinload(Blob.files).selectinload(File.folder))
                .order_by(Blob.accessed_at.asc())
                .limit(limit)
            ).unique()
        )

    def list_recently_accessed_candidates(
        self, *, recency_cutoff: dt.datetime, limit: int
    ) -> list[Blob]:
        return list(
            self._session.scalars(
                select(Blob)
                .where(Blob.refcount > 0, Blob.accessed_at >= recency_cutoff)
                .options(selectinload(Blob.files).selectinload(File.folder))
                .order_by(Blob.accessed_at.desc())
                .limit(limit)
            ).unique()
        )

    def save(self, blob: Blob) -> None:
        self._session.flush()


def build_blob_store(session: Session) -> BlobStore:
    return SqlAlchemyBlobStore(session)
