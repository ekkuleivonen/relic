"""Blob byte I/O via ``StorageRegistry`` (S3, filesystem, …)."""

import re
from io import BytesIO
from typing import Any, BinaryIO

from domain.exceptions import BadRequestError
from infra.db.models import Bucket
from ports.storage_registry import StorageRegistry

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


def _remote_object(bucket: Bucket, bucket_key: str) -> tuple[str, str]:
    return bucket.bucket, bucket_key


def _body_size(body: BinaryIO) -> int:
    pos = body.tell()
    body.seek(0, 2)
    size = body.tell()
    body.seek(pos)
    return size


def upload_blob(
    *,
    storage: StorageRegistry,
    bucket: Bucket,
    bucket_key: str,
    body: BinaryIO,
) -> None:
    adapter = storage.for_bucket(bucket)
    remote_bucket, key = _remote_object(bucket, bucket_key)
    adapter.put(
        bucket=remote_bucket,
        key=key,
        body=body,
        size=_body_size(body),
    )


def delete_blob_bytes(
    *,
    storage: StorageRegistry,
    bucket: Bucket,
    bucket_key: str,
) -> None:
    adapter = storage.for_bucket(bucket)
    remote_bucket, key = _remote_object(bucket, bucket_key)
    adapter.delete(bucket=remote_bucket, key=key)


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
    bucket: Bucket,
    bucket_key: str,
    range_header: str | None = None,
) -> dict[str, Any]:
    """Return a boto-shaped response dict with ``Body`` as a readable stream."""
    adapter = storage.for_bucket(bucket)
    remote_bucket, key = _remote_object(bucket, bucket_key)

    if range_header:
        total = adapter.head(bucket=remote_bucket, key=key)
        start, end, headers = _parse_range_header(range_header, total)
        data = adapter.get(bucket=remote_bucket, key=key, start=start, end=end)
        return {**headers, "Body": BytesIO(data)}

    data = adapter.get(bucket=remote_bucket, key=key)
    return {"ContentLength": len(data), "Body": BytesIO(data)}
