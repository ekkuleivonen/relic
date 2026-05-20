"""Streaming object storage tests."""

import io
from pathlib import Path

import pytest
from domain.exceptions import ResourceNotFound
from infra.gateway import blob_storage
from infra.object_storage.filesystem import FilesystemObjectStorage
from infra.object_storage.memory import MemoryObjectStorage
from infra.object_storage.streams import RangeLimitedReader
from ports.storage_registry import StorageRegistry
from tests.factories.models import StorageBackendFactory


class _Registry(StorageRegistry):
    def __init__(self, adapter) -> None:
        self._adapter = adapter

    def for_storage_backend(self, storage_backend):
        del storage_backend
        return self._adapter

    def for_storage_backend_id(self, session, storage_backend_id):
        del session, storage_backend_id
        return self._adapter


def test_filesystem_open_read_streams_without_loading_whole_file(tmp_path, monkeypatch) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    payload = b"a" * 256 * 1024
    storage.put(
        namespace="hot",
        key="large.bin",
        body=io.BytesIO(payload),
        size=len(payload),
    )

    read_calls: list[int] = []
    original_read_bytes = Path.read_bytes

    def tracked_read_bytes(self, *args, **kwargs):
        read_calls.append(1)
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)

    body, content_length = storage.open_read(namespace="hot", key="large.bin")
    try:
        assert content_length == len(payload)
        assert body.read(1024) == payload[:1024]
        assert body.read(1024) == payload[1024:2048]
    finally:
        body.close()

    assert read_calls == []


def test_filesystem_open_read_range(tmp_path) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    storage.put(
        namespace="hot",
        key="range.txt",
        body=io.BytesIO(b"0123456789"),
        size=10,
    )

    body, content_length = storage.open_read(
        namespace="hot",
        key="range.txt",
        start=2,
        end=5,
    )
    try:
        assert content_length == 4
        assert body.read() == b"2345"
    finally:
        body.close()


def test_fetch_blob_bytes_returns_streaming_body() -> None:
    adapter = MemoryObjectStorage()
    adapter.put(
        namespace="ns",
        key="obj.bin",
        body=io.BytesIO(b"hello-stream"),
        size=12,
    )
    bucket = StorageBackendFactory.build(namespace="ns")
    registry = _Registry(adapter)

    response = blob_storage.fetch_blob_bytes(
        storage=registry,
        bucket=bucket,
        bucket_key="obj.bin",
    )

    assert response["ContentLength"] == "12"
    body = response["Body"]
    try:
        assert body.read(5) == b"hello"
        assert body.read() == b"-stream"
    finally:
        body.close()


def test_range_limited_reader_stops_at_boundary() -> None:
    source = io.BytesIO(b"0123456789")
    reader = RangeLimitedReader(source, 4)
    try:
        assert reader.read() == b"0123"
        assert reader.read() == b""
    finally:
        reader.close()


def test_filesystem_get_still_returns_bytes(tmp_path) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    storage.put(
        namespace="hot",
        key="a/b.txt",
        body=io.BytesIO(b"hello"),
        size=5,
    )
    assert storage.get(namespace="hot", key="a/b.txt") == b"hello"
    storage.delete(namespace="hot", key="a/b.txt")
    with pytest.raises(ResourceNotFound):
        storage.get(namespace="hot", key="a/b.txt")
