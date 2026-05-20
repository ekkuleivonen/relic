"""Memory object storage tests."""

import pytest
from domain.exceptions import ResourceNotFound
from infra.object_storage.memory import MemoryObjectStorage


def test_memory_put_get_delete() -> None:
    storage = MemoryObjectStorage()
    result = storage.put(
        bucket="hot",
        key="a/b.txt",
        body=__import__("io").BytesIO(b"hello"),
        size=5,
    )
    assert result.etag
    assert storage.get(bucket="hot", key="a/b.txt") == b"hello"
    assert storage.head(bucket="hot", key="a/b.txt") == 5
    storage.delete(bucket="hot", key="a/b.txt")
    with pytest.raises(ResourceNotFound):
        storage.get(bucket="hot", key="a/b.txt")


def test_memory_copy() -> None:
    storage = MemoryObjectStorage()
    storage.put(
        bucket="src",
        key="file.bin",
        body=__import__("io").BytesIO(b"payload"),
        size=7,
    )
    storage.copy(
        src_bucket="src",
        src_key="file.bin",
        dest_bucket="dest",
        dest_key="copy.bin",
    )
    assert storage.get(bucket="dest", key="copy.bin") == b"payload"
