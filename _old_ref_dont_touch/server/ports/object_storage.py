"""Object byte storage port."""

from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class PutResult:
    etag: str


@dataclass(frozen=True)
class StorageCapabilities:
    multipart: bool = True
    ranged_reads: bool = True
    server_side_copy: bool = True
    list_prefix: bool = True
    presigned_urls: bool = True
    max_single_put_bytes: int | None = None


class ObjectStorage(Protocol):
    @property
    def capabilities(self) -> StorageCapabilities: ...

    def put(
        self, *, namespace: str, key: str, body: BinaryIO, size: int
    ) -> PutResult: ...

    def get(
        self, *, namespace: str, key: str, start: int | None = None, end: int | None = None
    ) -> bytes: ...

    def open_read(
        self,
        *,
        namespace: str,
        key: str,
        start: int | None = None,
        end: int | None = None,
    ) -> tuple[BinaryIO, int]:
        """Return ``(body, content_length)``. Caller must close ``body`` when done."""

    def head(self, *, namespace: str, key: str) -> int: ...

    def delete(self, *, namespace: str, key: str) -> None: ...

    def copy(
        self,
        *,
        src_namespace: str,
        src_key: str,
        dest_namespace: str,
        dest_key: str,
    ) -> PutResult: ...

    def compose_parts(
        self,
        *,
        namespace: str,
        dest_key: str,
        source_keys: list[str],
    ) -> PutResult: ...
