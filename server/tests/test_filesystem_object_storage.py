"""Filesystem object storage tests."""

import pytest
from domain.exceptions import ResourceNotFound
from infra.object_storage.filesystem import FilesystemObjectStorage


def test_filesystem_put_get_delete(tmp_path) -> None:
    storage = FilesystemObjectStorage(tmp_path)
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
