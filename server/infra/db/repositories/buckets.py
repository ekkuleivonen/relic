import datetime as dt
import uuid
from typing import Any

from domain.exceptions import ConflictError, ResourceNotFound
from infra.db.models import Blob, Bucket, BucketProbe
from ports.repositories.buckets import BucketStore
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session


class SqlAlchemyBucketStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, bucket_id: uuid.UUID) -> Bucket:
        bucket = self._session.get(Bucket, bucket_id)
        if bucket is None:
            raise ResourceNotFound("Bucket not found")
        return bucket

    def ensure_name_available(
        self, name: str, *, excluding_id: uuid.UUID | None = None
    ) -> None:
        query = select(Bucket).where(Bucket.name == name)
        if excluding_id is not None:
            query = query.where(Bucket.id != excluding_id)
        if self._session.scalar(query) is not None:
            raise ConflictError("A bucket with this name already exists")

    def add(self, bucket: Bucket) -> None:
        self._session.add(bucket)
        self._session.flush()

    def apply_updates(self, bucket: Bucket, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(bucket, key, value)
        self._session.flush()

    def delete(self, bucket: Bucket) -> None:
        self._session.delete(bucket)

    def blob_count(self, bucket_id: uuid.UUID) -> int:
        count = self._session.scalar(
            select(func.count()).select_from(Blob).where(Blob.bucket_id == bucket_id)
        )
        return int(count or 0)

    def add_probe(self, probe: BucketProbe) -> None:
        self._session.add(probe)
        self._session.flush()

    def delete_probes_older_than(self, cutoff: dt.datetime) -> int:
        result = self._session.execute(
            delete(BucketProbe).where(BucketProbe.observed_at < cutoff)
        )
        return int(result.rowcount or 0)

    def refresh(self, *entities: object) -> None:
        for entity in entities:
            self._session.refresh(entity)


def build_bucket_store(session: Session) -> BucketStore:
    return SqlAlchemyBucketStore(session)
