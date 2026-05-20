"""Storage registry adapter selection."""

from enums import StorageKind
from infra.object_storage.filesystem import FilesystemObjectStorage
from infra.object_storage.registry import S3ObjectStorage, SqlAlchemyStorageRegistry
from tests.factories.models import BucketFactory


def test_registry_returns_s3_adapter_by_default() -> None:
    bucket = BucketFactory.build(storage_kind=StorageKind.S3)
    adapter = SqlAlchemyStorageRegistry().for_bucket(bucket)
    assert isinstance(adapter, S3ObjectStorage)


def test_registry_returns_filesystem_adapter(tmp_path) -> None:
    bucket = BucketFactory.build(
        storage_kind=StorageKind.FILESYSTEM,
        endpoint=str(tmp_path),
        region="local",
        bucket="blobs",
        key_id="n/a",
        secret_access_key="n/a",
    )
    adapter = SqlAlchemyStorageRegistry().for_bucket(bucket)
    assert isinstance(adapter, FilesystemObjectStorage)
