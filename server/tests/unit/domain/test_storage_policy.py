import pytest
from domain.exceptions import BadRequestError
from ports.object_storage import StorageCapabilities
from ports.storage_policy import (
    enforce_max_object_bytes,
    enforce_multipart,
    enforce_server_side_copy,
    enforce_single_put_size,
)


def test_enforce_single_put_size_rejects_oversized():
    caps = StorageCapabilities(max_single_put_bytes=100)
    with pytest.raises(BadRequestError, match="exceeds maximum"):
        enforce_single_put_size(caps=caps, size_bytes=101)


def test_enforce_multipart_rejects_when_disabled():
    caps = StorageCapabilities(multipart=False)
    with pytest.raises(BadRequestError, match="Multipart"):
        enforce_multipart(caps=caps)


def test_enforce_server_side_copy_rejects_when_disabled():
    caps = StorageCapabilities(server_side_copy=False)
    with pytest.raises(BadRequestError, match="Server-side copy"):
        enforce_server_side_copy(caps=caps)


def test_enforce_max_object_bytes_rejects_oversized(monkeypatch):
    monkeypatch.setattr("ports.storage_policy.S.MAX_OBJECT_BYTES", 10)
    with pytest.raises(BadRequestError, match="maximum allowed size"):
        enforce_max_object_bytes(size_bytes=11)
