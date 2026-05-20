"""Per-bucket object storage adapter selection."""

import hashlib
import uuid
from io import BytesIO
from typing import BinaryIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from domain.exceptions import BadRequestError, ResourceNotFound
from enums import StorageKind
from infra.db.models import Bucket
from infra.object_storage.filesystem import FilesystemObjectStorage
from ports.object_storage import ObjectStorage, PutResult, StorageCapabilities
from ports.storage_registry import StorageRegistry
from sqlalchemy.orm import Session
from utils.logging import get_logger

log = get_logger(__name__)


class S3ObjectStorage:
    """S3-compatible adapter backed by boto3."""

    def __init__(self, bucket: Bucket) -> None:
        self._bucket = bucket

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities()

    def _client(self):
        return boto3.client(
            service_name="s3",
            endpoint_url=self._bucket.endpoint,
            region_name=self._bucket.region,
            aws_access_key_id=self._bucket.key_id,
            aws_secret_access_key=self._bucket.secret_access_key,
        )

    def put(
        self, *, bucket: str, key: str, body: BinaryIO, size: int
    ) -> PutResult:
        del bucket, size
        try:
            body.seek(0)
            response = self._client().put_object(
                Bucket=self._bucket.bucket,
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
                bucket_id=str(self._bucket.id),
                key=key,
                error=str(exc),
            )
            raise BadRequestError("Failed to upload object to bucket") from exc

    def get(
        self, *, bucket: str, key: str, start: int | None = None, end: int | None = None
    ) -> bytes:
        del bucket
        try:
            params: dict = {"Bucket": self._bucket.bucket, "Key": key}
            if start is not None or end is not None:
                end_suffix = "" if end is None else str(end)
                params["Range"] = f"bytes={start or 0}-{end_suffix}"
            response = self._client().get_object(**params)
            return response["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise ResourceNotFound("Object not found") from exc

    def head(self, *, bucket: str, key: str) -> int:
        del bucket
        try:
            response = self._client().head_object(
                Bucket=self._bucket.bucket,
                Key=key,
            )
            return int(response["ContentLength"])
        except (BotoCoreError, ClientError) as exc:
            raise ResourceNotFound("Object not found") from exc

    def delete(self, *, bucket: str, key: str) -> None:
        del bucket
        try:
            self._client().delete_object(Bucket=self._bucket.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            log.warning(
                "s3_delete_failed",
                bucket_id=str(self._bucket.id),
                key=key,
                error=str(exc),
            )
            raise BadRequestError("Failed to delete object from bucket") from exc

    def copy(
        self,
        *,
        src_bucket: str,
        src_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> PutResult:
        del src_bucket, dest_bucket
        try:
            response = self._client().copy_object(
                Bucket=self._bucket.bucket,
                Key=dest_key,
                CopySource={"Bucket": self._bucket.bucket, "Key": src_key},
            )
            etag = response.get("CopyObjectResult", {}).get("ETag", "").strip('"')
            return PutResult(etag=etag or "")
        except (BotoCoreError, ClientError) as exc:
            raise BadRequestError("Failed to copy object in bucket") from exc

    def compose_parts(
        self,
        *,
        bucket: str,
        dest_key: str,
        source_keys: list[str],
    ) -> PutResult:
        del bucket
        client = self._client()
        upload_id = None
        try:
            created = client.create_multipart_upload(
                Bucket=self._bucket.bucket,
                Key=dest_key,
            )
            upload_id = created["UploadId"]
            completed_parts = []
            for index, source_key in enumerate(source_keys, start=1):
                response = client.upload_part_copy(
                    Bucket=self._bucket.bucket,
                    Key=dest_key,
                    UploadId=upload_id,
                    PartNumber=index,
                    CopySource={"Bucket": self._bucket.bucket, "Key": source_key},
                )
                etag = response.get("CopyPartResult", {}).get("ETag", "").strip('"')
                completed_parts.append({"PartNumber": index, "ETag": etag})
            completed = client.complete_multipart_upload(
                Bucket=self._bucket.bucket,
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
                        Bucket=self._bucket.bucket,
                        Key=dest_key,
                        UploadId=upload_id,
                    )
                except (BotoCoreError, ClientError):
                    pass
            raise BadRequestError("Failed to compose multipart object") from exc


class SqlAlchemyStorageRegistry:
    """Per-bucket adapter selection by ``Bucket.storage_kind``."""

    def for_bucket(self, bucket: Bucket) -> ObjectStorage:
        if bucket.storage_kind == StorageKind.FILESYSTEM:
            return FilesystemObjectStorage(bucket.endpoint)
        return S3ObjectStorage(bucket)

    def for_bucket_id(self, session: Session, bucket_id: uuid.UUID) -> ObjectStorage:
        bucket = session.get(Bucket, bucket_id)
        if bucket is None:
            raise ResourceNotFound("Bucket not found")
        return self.for_bucket(bucket)


def build_storage_registry() -> StorageRegistry:
    return SqlAlchemyStorageRegistry()
