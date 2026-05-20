import datetime as dt
import uuid

from infra.db.models import MultipartUpload, MultipartUploadPart
from ports.repositories.multipart import MultipartStore
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload


class SqlAlchemyMultipartStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, upload: MultipartUpload) -> MultipartUpload:
        self._session.add(upload)
        self._session.flush()
        return upload

    def get(
        self,
        upload_id: uuid.UUID,
        *,
        with_parts: bool = False,
    ) -> MultipartUpload | None:
        stmt = select(MultipartUpload).where(MultipartUpload.id == upload_id)
        if with_parts:
            stmt = stmt.options(
                selectinload(MultipartUpload.parts),
                selectinload(MultipartUpload.storage_bucket),
            )
        return self._session.scalar(stmt)

    def save_part(self, part: MultipartUploadPart) -> MultipartUploadPart:
        self._session.add(part)
        self._session.flush()
        return part

    def get_part(
        self, upload_id: uuid.UUID, part_number: int
    ) -> MultipartUploadPart | None:
        return self._session.scalar(
            select(MultipartUploadPart).where(
                MultipartUploadPart.upload_id == upload_id,
                MultipartUploadPart.part_number == part_number,
            )
        )

    def delete(self, upload: MultipartUpload) -> None:
        self._session.delete(upload)

    def list_for_bucket(self, bucket_name: str) -> list[MultipartUpload]:
        return list(
            self._session.scalars(
                select(MultipartUpload)
                .where(MultipartUpload.bucket_name == bucket_name)
                .order_by(MultipartUpload.created_at.asc(), MultipartUpload.id.asc())
            )
        )

    def list_stale_before(self, cutoff: dt.datetime) -> list[MultipartUpload]:
        return list(
            self._session.scalars(
                select(MultipartUpload)
                .where(MultipartUpload.created_at < cutoff)
                .options(
                    selectinload(MultipartUpload.parts),
                    selectinload(MultipartUpload.storage_bucket),
                )
            )
        )


def build_multipart_store(session: Session) -> MultipartStore:
    return SqlAlchemyMultipartStore(session)
