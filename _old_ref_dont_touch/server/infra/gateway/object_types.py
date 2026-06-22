import uuid
from dataclasses import dataclass
from typing import Any

from infra.db.models import Blob, StorageBackend, File


@dataclass(frozen=True)
class PutObjectResult:
    file: File
    blob: Blob
    etag: str
    created: bool
    previous_blob_id: uuid.UUID | None = None


@dataclass(frozen=True)
class CopyObjectResult:
    file: File
    blob: Blob
    etag: str
    source_file_id: uuid.UUID | None = None


@dataclass(frozen=True)
class GetObjectResult:
    file: File
    blob: Blob
    bucket: StorageBackend


@dataclass(frozen=True)
class GetObjectBytesResult:
    result: GetObjectResult
    boto_response: dict[str, Any]


@dataclass(frozen=True)
class DeleteObjectResult:
    """Result of a DELETE call. existed=False when the key was already absent."""

    existed: bool


@dataclass(frozen=True)
class CreateBlobResult:
    blob: Blob
    remote_latency_ms: int
