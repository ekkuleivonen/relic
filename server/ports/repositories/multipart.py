import datetime as dt
import uuid
from typing import Protocol

from infra.db.models import MultipartUpload, MultipartUploadPart


class MultipartStore(Protocol):
    def create(self, upload: MultipartUpload) -> MultipartUpload: ...

    def get(
        self,
        upload_id: uuid.UUID,
        *,
        with_parts: bool = False,
    ) -> MultipartUpload | None: ...

    def save_part(self, part: MultipartUploadPart) -> MultipartUploadPart: ...

    def get_part(
        self, upload_id: uuid.UUID, part_number: int
    ) -> MultipartUploadPart | None: ...

    def delete(self, upload: MultipartUpload) -> None: ...

    def list_for_storage_backend(self, bucket_name: str) -> list[MultipartUpload]: ...

    def list_stale_before(self, cutoff: dt.datetime) -> list[MultipartUpload]: ...
