"""Local filesystem object storage (hot NVMe / embedded mode)."""

import os
import shutil
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from domain.exceptions import ResourceNotFound
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

    def _path(self, bucket: str, key: str) -> Path:
        return self._base / bucket / key

    def put(
        self, *, bucket: str, key: str, body: BinaryIO, size: int
    ) -> PutResult:
        path = self._path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as handle:
            shutil.copyfileobj(body, handle)
        os.replace(tmp, path)
        import hashlib

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return PutResult(etag=digest)

    def get(
        self, *, bucket: str, key: str, start: int | None = None, end: int | None = None
    ) -> bytes:
        path = self._path(bucket, key)
        if not path.is_file():
            raise ResourceNotFound("Object not found")
        data = path.read_bytes()
        if start is None and end is None:
            return data
        return data[start : (end + 1 if end is not None else None)]

    def head(self, *, bucket: str, key: str) -> int:
        path = self._path(bucket, key)
        if not path.is_file():
            raise ResourceNotFound("Object not found")
        return path.stat().st_size

    def delete(self, *, bucket: str, key: str) -> None:
        path = self._path(bucket, key)
        if path.is_file():
            path.unlink()

    def copy(
        self,
        *,
        src_bucket: str,
        src_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> PutResult:
        src = self._path(src_bucket, src_key)
        dest = self._path(dest_bucket, dest_key)
        if not src.is_file():
            raise ResourceNotFound("Object not found")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        import hashlib

        return PutResult(etag=hashlib.sha256(dest.read_bytes()).hexdigest())

    def compose_parts(
        self,
        *,
        bucket: str,
        dest_key: str,
        source_keys: list[str],
    ) -> PutResult:
        dest = self._path(bucket, dest_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        with open(tmp, "wb") as output:
            for source_key in source_keys:
                src = self._path(bucket, source_key)
                if not src.is_file():
                    raise ResourceNotFound("Object not found")
                with open(src, "rb") as source:
                    shutil.copyfileobj(source, output)
        os.replace(tmp, dest)
        import hashlib

        return PutResult(etag=hashlib.sha256(dest.read_bytes()).hexdigest())
