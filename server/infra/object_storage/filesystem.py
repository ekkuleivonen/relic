"""Local filesystem object storage (hot NVMe / embedded mode)."""

import os
import shutil
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from domain.exceptions import ResourceNotFound
from infra.object_storage.streams import RangeLimitedReader
from ports.object_storage import ObjectStorage, PutResult, StorageCapabilities


class FilesystemObjectStorage:
    def __init__(self, base_path: str | Path) -> None:
        self._base = Path(base_path)

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities(
            multipart=True,
            presigned_urls=False,
            max_single_put_bytes=512 * 1024 * 1024,
        )

    def _path(self, namespace: str, key: str) -> Path:
        return self._base / namespace / key

    def put(
        self, *, namespace: str, key: str, body: BinaryIO, size: int
    ) -> PutResult:
        del size
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as handle:
            shutil.copyfileobj(body, handle)
        os.replace(tmp, path)
        import hashlib

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return PutResult(etag=digest)

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
        path = self._path(namespace, key)
        if not path.is_file():
            raise ResourceNotFound("Object not found")
        total = path.stat().st_size
        if start is None and end is None:
            handle = open(path, "rb")
            return handle, total

        read_start = start or 0
        read_end = total - 1 if end is None else min(end, total - 1)
        if read_start >= total:
            return BytesIO(b""), 0
        handle = open(path, "rb")
        handle.seek(read_start)
        length = read_end - read_start + 1
        return RangeLimitedReader(handle, length), length

    def head(self, *, namespace: str, key: str) -> int:
        path = self._path(namespace, key)
        if not path.is_file():
            raise ResourceNotFound("Object not found")
        return path.stat().st_size

    def delete(self, *, namespace: str, key: str) -> None:
        path = self._path(namespace, key)
        if path.is_file():
            path.unlink()

    def copy(
        self,
        *,
        src_namespace: str,
        src_key: str,
        dest_namespace: str,
        dest_key: str,
    ) -> PutResult:
        src = self._path(src_namespace, src_key)
        dest = self._path(dest_namespace, dest_key)
        if not src.is_file():
            raise ResourceNotFound("Object not found")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        import hashlib

        return PutResult(etag=hashlib.sha256(dest.read_bytes()).hexdigest())

    def compose_parts(
        self,
        *,
        namespace: str,
        dest_key: str,
        source_keys: list[str],
    ) -> PutResult:
        dest = self._path(namespace, dest_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        with open(tmp, "wb") as output:
            for source_key in source_keys:
                src = self._path(namespace, source_key)
                if not src.is_file():
                    raise ResourceNotFound("Object not found")
                with open(src, "rb") as source:
                    shutil.copyfileobj(source, output)
        os.replace(tmp, dest)
        import hashlib

        return PutResult(etag=hashlib.sha256(dest.read_bytes()).hexdigest())
