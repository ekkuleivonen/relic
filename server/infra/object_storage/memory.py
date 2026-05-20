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
        self, *, bucket: str, key: str, body: BinaryIO, size: int
    ) -> PutResult:
        data = body.read(size)
        self._objects[(bucket, key)] = data
        return PutResult(etag=hashlib.sha256(data).hexdigest())

    def get(
        self, *, bucket: str, key: str, start: int | None = None, end: int | None = None
    ) -> bytes:
        data = self._objects.get((bucket, key))
        if data is None:
            raise ResourceNotFound("Object not found")
        if start is None and end is None:
            return data
        return data[start : (end + 1 if end is not None else None)]

    def head(self, *, bucket: str, key: str) -> int:
        data = self._objects.get((bucket, key))
        if data is None:
            raise ResourceNotFound("Object not found")
        return len(data)

    def delete(self, *, bucket: str, key: str) -> None:
        self._objects.pop((bucket, key), None)

    def copy(
        self,
        *,
        src_bucket: str,
        src_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> PutResult:
        data = self.get(bucket=src_bucket, key=src_key)
        return self.put(
            bucket=dest_bucket,
            key=dest_key,
            body=BytesIO(data),
            size=len(data),
        )
