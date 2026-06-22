import datetime as dt
import uuid
from typing import Protocol

from infra.db.models import Blob


class BlobStore(Protocol):
    def get(self, blob_id: uuid.UUID) -> Blob: ...

    def touch_access(
        self, blob: Blob, *, debounce_minutes: int | None = None
    ) -> bool: ...

    def list_dereferenced_for_purge(self, *, batch: int) -> list[Blob]: ...

    def delete_row(self, blob: Blob) -> None: ...

    def list_pressured_candidates(
        self, *, storage_backend_ids: set[uuid.UUID], limit: int
    ) -> list[Blob]: ...

    def list_recently_accessed_candidates(
        self, *, recency_cutoff: dt.datetime, limit: int
    ) -> list[Blob]: ...

    def save(self, blob: Blob) -> None: ...
