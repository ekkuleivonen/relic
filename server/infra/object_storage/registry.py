"""Per-bucket object storage adapter selection."""

import hashlib
import uuid
from io import BytesIO
from typing import BinaryIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from domain.exceptions import BadRequestError, ResourceNotFound
from enums import StorageBackendKind
from infra.db.models import StorageBackend
from infra.object_storage.azure_blob import AzureBlobObjectStorage
from infra.object_storage.filesystem import FilesystemObjectStorage
from infra.object_storage.gcs import GcsObjectStorage
from ports.object_storage import ObjectStorage, PutResult, StorageCapabilities
from ports.storage_registry import StorageRegistry
from sqlalchemy.orm import Session
from utils.logging import get_logger

log = get_logger(__name__)


class S3ObjectStorage:
    """S3-compatible adapter backed by boto3."""

    def __init__(self, storage_backend: StorageBackend) -> None:
        self._storage_backend = storage_backend

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities()

    def _client(self):
        return boto3.client(
            service_name="s3",
            endpoint_url=self._storage_backend.endpoint,
            region_name=self._storage_backend.region,
            aws_access_key_id=self._storage_backend.key_id,
            aws_secret_access_key=self._storage_backend.secret_access_key,
        )

    def put(
        self, *, namespace: str, key: str, body: BinaryIO, size: int
    ) -> PutResult:
        del namespace, size
        try:
            body.seek(0)
            response = self._client().put_object(
                Bucket=self._storage_backend.namespace,
                Key=key,
                Body=body,
            )
            etag = ""
            if isinstance(response, dict):
                etag = response.get("ETag", "").strip('"') or ""
            if not etag:
                body.seek(0)
                etag = hashlib.sha256(body.read()).hexdigest()
                body.seek(0)
            return PutResult(etag=etag)
        except (BotoCoreError, ClientError) as exc:
            log.warning(
                "s3_put_failed",
                storage_backend_id=str(self._storage_backend.id),
                key=key,
                error=str(exc),
            )
            raise BadRequestError("Failed to upload object to storage backend") from exc

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
        del namespace
        try:
            params: dict = {"Bucket": self._storage_backend.namespace, "Key": key}
            if start is not None or end is not None:
                end_suffix = "" if end is None else str(end)
                params["Range"] = f"bytes={start or 0}-{end_suffix}"
            response = self._client().get_object(**params)
            body = response["Body"]
            content_length = int(response["ContentLength"])
            return body, content_length
        except (BotoCoreError, ClientError) as exc:
            raise ResourceNotFound("Object not found") from exc

    def head(self, *, namespace: str, key: str) -> int:
        del namespace
        try:
            response = self._client().head_object(
                Bucket=self._storage_backend.namespace,
                Key=key,
            )
            return int(response["ContentLength"])
        except (BotoCoreError, ClientError) as exc:
            raise ResourceNotFound("Object not found") from exc

    def delete(self, *, namespace: str, key: str) -> None:
        del namespace
        try:
            self._client().delete_object(Bucket=self._storage_backend.namespace, Key=key)
        except (BotoCoreError, ClientError) as exc:
            log.warning(
                "s3_delete_failed",
                storage_backend_id=str(self._storage_backend.id),
                key=key,
                error=str(exc),
            )
            raise BadRequestError("Failed to delete object from storage backend") from exc

    def copy(
        self,
        *,
        src_namespace: str,
        src_key: str,
        dest_namespace: str,
        dest_key: str,
    ) -> PutResult:
        del src_namespace, dest_namespace
        try:
            response = self._client().copy_object(
                Bucket=self._storage_backend.namespace,
                Key=dest_key,
                CopySource={"Bucket": self._storage_backend.namespace, "Key": src_key},
            )
            etag = response.get("CopyObjectResult", {}).get("ETag", "").strip('"')
            return PutResult(etag=etag or "")
        except (BotoCoreError, ClientError) as exc:
            raise BadRequestError("Failed to copy object in storage backend") from exc

    def compose_parts(
        self,
        *,
        namespace: str,
        dest_key: str,
        source_keys: list[str],
    ) -> PutResult:
        del namespace
        client = self._client()
        upload_id = None
        try:
            created = client.create_multipart_upload(
                Bucket=self._storage_backend.namespace,
                Key=dest_key,
            )
            upload_id = created["UploadId"]
            completed_parts = []
            for index, source_key in enumerate(source_keys, start=1):
                response = client.upload_part_copy(
                    Bucket=self._storage_backend.namespace,
                    Key=dest_key,
                    UploadId=upload_id,
                    PartNumber=index,
                    CopySource={"Bucket": self._storage_backend.namespace, "Key": source_key},
                )
                etag = response.get("CopyPartResult", {}).get("ETag", "").strip('"')
                completed_parts.append({"PartNumber": index, "ETag": etag})
            completed = client.complete_multipart_upload(
                Bucket=self._storage_backend.namespace,
                Key=dest_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": completed_parts},
            )
            etag = completed.get("ETag", "").strip('"')
            return PutResult(etag=etag)
        except (BotoCoreError, ClientError) as exc:
            if upload_id:
                try:
                    client.abort_multipart_upload(
                        Bucket=self._storage_backend.namespace,
                        Key=dest_key,
                        UploadId=upload_id,
                    )
                except (BotoCoreError, ClientError):
                    pass
            raise BadRequestError("Failed to compose multipart object") from exc


class SqlAlchemyStorageRegistry:
    """Per-storage-backend adapter selection by ``StorageBackend.kind``."""

    def for_storage_backend(self, storage_backend: StorageBackend) -> ObjectStorage:
        if storage_backend.kind == StorageBackendKind.FILESYSTEM:
            return FilesystemObjectStorage(storage_backend.endpoint)
        if storage_backend.kind == StorageBackendKind.AZURE_BLOB:
            return AzureBlobObjectStorage(storage_backend.endpoint)
        if storage_backend.kind == StorageBackendKind.GCS:
            return GcsObjectStorage(storage_backend.endpoint)
        return S3ObjectStorage(storage_backend)

    def for_storage_backend_id(self, session: Session, storage_backend_id: uuid.UUID) -> ObjectStorage:
        storage_backend = session.get(StorageBackend, storage_backend_id)
        if storage_backend is None:
            raise ResourceNotFound("Storage backend not found")
        return self.for_storage_backend(storage_backend)


def build_storage_registry() -> StorageRegistry:
    return SqlAlchemyStorageRegistry()
