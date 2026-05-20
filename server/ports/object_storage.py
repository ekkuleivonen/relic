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
        self, *, bucket: str, key: str, body: BinaryIO, size: int
    ) -> PutResult: ...

    def get(
        self, *, bucket: str, key: str, start: int | None = None, end: int | None = None
    ) -> bytes: ...

    def head(self, *, bucket: str, key: str) -> int: ...

    def delete(self, *, bucket: str, key: str) -> None: ...

    def copy(
        self,
        *,
        src_bucket: str,
        src_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> PutResult: ...
