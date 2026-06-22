"""Memory object storage tests."""

import pytest
from domain.exceptions import ResourceNotFound
from infra.object_storage.memory import MemoryObjectStorage


def test_memory_put_get_delete() -> None:
    storage = MemoryObjectStorage()
    result = storage.put(
        namespace="hot",
        key="a/b.txt",
        body=__import__("io").BytesIO(b"hello"),
        size=5,
    )
    assert result.etag
    assert storage.get(namespace="hot", key="a/b.txt") == b"hello"
    assert storage.head(namespace="hot", key="a/b.txt") == 5
    storage.delete(namespace="hot", key="a/b.txt")
    with pytest.raises(ResourceNotFound):
        storage.get(namespace="hot", key="a/b.txt")


def test_memory_copy() -> None:
    storage = MemoryObjectStorage()
    storage.put(
        namespace="src",
        key="file.bin",
        body=__import__("io").BytesIO(b"payload"),
        size=7,
    )
    storage.copy(
        src_namespace="src",
        src_key="file.bin",
        dest_namespace="dest",
        dest_key="copy.bin",
    )
    assert storage.get(namespace="dest", key="copy.bin") == b"payload"
