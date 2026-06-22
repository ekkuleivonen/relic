"""Storage registry adapter selection."""

from enums import StorageBackendKind
from infra.object_storage.filesystem import FilesystemObjectStorage
from infra.object_storage.registry import S3ObjectStorage, SqlAlchemyStorageRegistry
from tests.factories.models import StorageBackendFactory


def test_registry_returns_s3_adapter_by_default() -> None:
    bucket = StorageBackendFactory.build(kind=StorageBackendKind.S3)
    adapter = SqlAlchemyStorageRegistry().for_storage_backend(bucket)
    assert isinstance(adapter, S3ObjectStorage)


def test_registry_returns_filesystem_adapter(tmp_path) -> None:
    bucket = StorageBackendFactory.build(
        kind=StorageBackendKind.FILESYSTEM,
        endpoint=str(tmp_path),
        region="local",
        namespace="blobs",
        key_id="n/a",
        secret_access_key="n/a",
    )
    adapter = SqlAlchemyStorageRegistry().for_storage_backend(bucket)
    assert isinstance(adapter, FilesystemObjectStorage)
