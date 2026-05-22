"""Blob byte I/O via ``StorageRegistry`` (S3, filesystem, …)."""

import re
from typing import Any, BinaryIO

from domain.exceptions import BadRequestError
from infra import metrics
from infra.db.models import StorageBackend
from ports.storage_registry import StorageRegistry

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


def _remote_object(bucket: StorageBackend, bucket_key: str) -> tuple[str, str]:
    return bucket.namespace, bucket_key


def _body_size(body: BinaryIO) -> int:
    pos = body.tell()
    body.seek(0, 2)
    size = body.tell()
    body.seek(pos)
    return size


def upload_blob(
    *,
    storage: StorageRegistry,
    bucket: StorageBackend,
    bucket_key: str,
    body: BinaryIO,
    operation: str = "put_object",
) -> None:
    size_bytes = _body_size(body)
    adapter = storage.for_storage_backend(bucket)
    remote_bucket, key = _remote_object(bucket, bucket_key)
    adapter.put(
        namespace=remote_bucket,
        key=key,
        body=body,
        size=size_bytes,
    )
    metrics.observe_gateway_bytes(
        operation=operation,
        direction="write",
        bytes_count=size_bytes,
    )
    metrics.observe_gateway_object_size(operation=operation, size_bytes=size_bytes)


def delete_blob_bytes(
    *,
    storage: StorageRegistry,
    bucket: StorageBackend,
    bucket_key: str,
) -> None:
    adapter = storage.for_storage_backend(bucket)
    remote_bucket, key = _remote_object(bucket, bucket_key)
    adapter.delete(namespace=remote_bucket, key=key)


def _parse_range_header(range_header: str, total_size: int) -> tuple[int, int, dict[str, str]]:
    match = _RANGE_RE.match(range_header.strip())
    if not match:
        raise BadRequestError("Invalid Range header")
    start = int(match.group(1))
    end_str = match.group(2)
    end = int(end_str) if end_str else total_size - 1
    if start >= total_size:
        raise BadRequestError("Invalid Range header")
    end = min(end, total_size - 1)
    length = end - start + 1
    return start, end, {
        "ContentRange": f"bytes {start}-{end}/{total_size}",
        "ContentLength": str(length),
    }


def fetch_blob_bytes(
    *,
    storage: StorageRegistry,
    bucket: StorageBackend,
    bucket_key: str,
    range_header: str | None = None,
    operation: str = "get_object",
) -> dict[str, Any]:
    """Return a boto-shaped response dict with ``Body`` as a readable stream."""
    adapter = storage.for_storage_backend(bucket)
    remote_bucket, key = _remote_object(bucket, bucket_key)

    if range_header:
        total = adapter.head(namespace=remote_bucket, key=key)
        start, end, headers = _parse_range_header(range_header, total)
        body, _content_length = adapter.open_read(
            namespace=remote_bucket,
            key=key,
            start=start,
            end=end,
        )
        bytes_count = end - start + 1
        metrics.observe_gateway_bytes(
            operation=operation,
            direction="read",
            bytes_count=bytes_count,
        )
        metrics.observe_gateway_object_size(operation=operation, size_bytes=bytes_count)
        return {**headers, "Body": body}

    body, content_length = adapter.open_read(namespace=remote_bucket, key=key)
    metrics.observe_gateway_bytes(
        operation=operation,
        direction="read",
        bytes_count=content_length,
    )
    metrics.observe_gateway_object_size(operation=operation, size_bytes=content_length)
    return {"ContentLength": str(content_length), "Body": body}
