"""In-memory object storage for tests and lightweight local runs."""

import hashlib
from io import BytesIO
from typing import BinaryIO

from domain.exceptions import ResourceNotFound
from ports.object_storage import PutResult, StorageCapabilities


class MemoryObjectStorage:
    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities(
            multipart=False,
            presigned_urls=False,
            max_single_put_bytes=16 * 1024 * 1024,
        )

    def put(
        self, *, namespace: str, key: str, body: BinaryIO, size: int
    ) -> PutResult:
        data = body.read(size)
        self._objects[(namespace, key)] = data
        return PutResult(etag=hashlib.sha256(data).hexdigest())

    def get(
        self, *, namespace: str, key: str, start: int | None = None, end: int | None = None
    ) -> bytes:
        body, _content_length = self.open_read(
            namespace=namespace, key=key, start=start, end=end
        )
        try:
            return body.read()
        finally:
            body.close()

    def open_read(
        self,
        *,
        namespace: str,
        key: str,
        start: int | None = None,
        end: int | None = None,
    ) -> tuple[BinaryIO, int]:
        data = self._objects.get((namespace, key))
        if data is None:
            raise ResourceNotFound("Object not found")
        if start is None and end is None:
            return BytesIO(data), len(data)
        slice_start = start or 0
        slice_end = None if end is None else end + 1
        sliced = data[slice_start:slice_end]
        return BytesIO(sliced), len(sliced)

    def head(self, *, namespace: str, key: str) -> int:
        data = self._objects.get((namespace, key))
        if data is None:
            raise ResourceNotFound("Object not found")
        return len(data)

    def delete(self, *, namespace: str, key: str) -> None:
        self._objects.pop((namespace, key), None)

    def copy(
        self,
        *,
        src_namespace: str,
        src_key: str,
        dest_namespace: str,
        dest_key: str,
    ) -> PutResult:
        data = self.get(namespace=src_namespace, key=src_key)
        return self.put(
            namespace=dest_namespace,
            key=dest_key,
            body=BytesIO(data),
            size=len(data),
        )

    def compose_parts(
        self,
        *,
        namespace: str,
        dest_key: str,
        source_keys: list[str],
    ) -> PutResult:
        data = b"".join(
            self.get(namespace=namespace, key=source_key) for source_key in source_keys
        )
        return self.put(
            namespace=namespace,
            key=dest_key,
            body=BytesIO(data),
            size=len(data),
        )
