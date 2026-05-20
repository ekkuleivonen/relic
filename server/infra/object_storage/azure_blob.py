"""Azure Blob Storage adapter (stub)."""

from typing import BinaryIO

from ports.object_storage import ObjectStorage, PutResult, StorageCapabilities


class AzureBlobObjectStorage:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    @property
    def capabilities(self) -> StorageCapabilities:
        raise NotImplementedError

    def put(
        self, *, namespace: str, key: str, body: BinaryIO, size: int
    ) -> PutResult:
        raise NotImplementedError

    def get(
        self,
        *,
        namespace: str,
        key: str,
        start: int | None = None,
        end: int | None = None,
    ) -> bytes:
        raise NotImplementedError

    def open_read(
        self,
        *,
        namespace: str,
        key: str,
        start: int | None = None,
        end: int | None = None,
    ) -> tuple[BinaryIO, int]:
        raise NotImplementedError

    def head(self, *, namespace: str, key: str) -> int:
        raise NotImplementedError

    def delete(self, *, namespace: str, key: str) -> None:
        raise NotImplementedError

    def copy(
        self,
        *,
        src_namespace: str,
        src_key: str,
        dest_namespace: str,
        dest_key: str,
    ) -> PutResult:
        raise NotImplementedError

    def compose_parts(
        self,
        *,
        namespace: str,
        dest_key: str,
        source_keys: list[str],
    ) -> PutResult:
        raise NotImplementedError
