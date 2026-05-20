"""S3-compatible XML response builders."""

import uuid
from xml.sax.saxutils import escape

from infra.gateway import object_listing
from infra.gateway import object_multipart
from infra.gateway.object_types import GetObjectResult
from domain.exceptions import (
    BadRequestError,
    ConflictError,
    DomainError,
    PermissionDenied,
    ResourceNotFound,
)
from fastapi import Response


def format_s3_timestamp(value) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def s3_error_response(code: str, message: str, *, status_code: int) -> Response:
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Error>"
        f"<Code>{escape(code)}</Code>"
        f"<Message>{escape(message)}</Message>"
        "</Error>"
    )
    return Response(
        content=body,
        status_code=status_code,
        media_type="application/xml",
    )


def domain_error_response(exc: DomainError) -> Response:
    if isinstance(exc, ConflictError):
        return s3_error_response("Conflict", str(exc.detail), status_code=409)
    if isinstance(exc, BadRequestError):
        message = str(exc.detail)
        if "exceeds maximum allowed size" in message:
            return s3_error_response("EntityTooLarge", message, status_code=400)
        return s3_error_response("InvalidRequest", message, status_code=400)
    if isinstance(exc, ResourceNotFound):
        return s3_error_response("NoSuchKey", str(exc.detail), status_code=404)
    if isinstance(exc, PermissionDenied):
        return s3_error_response("AccessDenied", str(exc.detail), status_code=403)
    return s3_error_response("AccessDenied", "Access denied", status_code=403)


def multipart_not_found_response(exc: ResourceNotFound) -> Response:
    message = str(exc.detail)
    if "Multipart upload" in message:
        return s3_error_response("NoSuchUpload", message, status_code=404)
    return s3_error_response("NoSuchBucket", message, status_code=404)


def render_list_buckets(*, owner_id: str, owner_name: str, buckets) -> str:
    bucket_xml = "".join(
        "<Bucket>"
        f"<Name>{escape(bucket.name)}</Name>"
        f"<CreationDate>{format_s3_timestamp(bucket.created_at)}</CreationDate>"
        "</Bucket>"
        for bucket in buckets
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ListAllMyBucketsResult>"
        "<Owner>"
        f"<ID>{escape(owner_id)}</ID>"
        f"<DisplayName>{escape(owner_name)}</DisplayName>"
        "</Owner>"
        f"<Buckets>{bucket_xml}</Buckets>"
        "</ListAllMyBucketsResult>"
    )


def render_list_objects_v2(page: object_listing.ListObjectsV2Page) -> str:
    contents = "".join(
        "<Contents>"
        f"<Key>{escape(item.key)}</Key>"
        f"<LastModified>{format_s3_timestamp(item.file.updated_at)}</LastModified>"
        f"<ETag>&quot;{item.file.blob.content_hash.hex()}&quot;</ETag>"
        f"<Size>{item.file.blob.size_bytes}</Size>"
        "<StorageClass>STANDARD</StorageClass>"
        "</Contents>"
        for item in page.contents
    )
    common_prefixes = "".join(
        f"<CommonPrefixes><Prefix>{escape(prefix)}</Prefix></CommonPrefixes>"
        for prefix in page.common_prefixes
    )
    delimiter = (
        f"<Delimiter>{escape(page.delimiter)}</Delimiter>" if page.delimiter else ""
    )
    continuation_token = (
        f"<ContinuationToken>{escape(page.continuation_token)}</ContinuationToken>"
        if page.continuation_token
        else ""
    )
    next_token = (
        f"<NextContinuationToken>{escape(page.next_continuation_token)}</NextContinuationToken>"
        if page.next_continuation_token
        else ""
    )
    start_after = (
        f"<StartAfter>{escape(page.start_after)}</StartAfter>"
        if page.start_after
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ListBucketResult>"
        f"<Name>{escape(page.bucket)}</Name>"
        f"<Prefix>{escape(page.prefix)}</Prefix>"
        f"{delimiter}"
        f"<KeyCount>{page.key_count}</KeyCount>"
        f"<MaxKeys>{page.max_keys}</MaxKeys>"
        f"<IsTruncated>{str(page.is_truncated).lower()}</IsTruncated>"
        f"{continuation_token}"
        f"{next_token}"
        f"{start_after}"
        f"{contents}"
        f"{common_prefixes}"
        "</ListBucketResult>"
    )


def render_list_multipart_uploads(
    bucket: str, page: object_multipart.MultipartUploadListPage
) -> str:
    uploads = "".join(
        "<Upload>"
        f"<Key>{escape(upload.object_key)}</Key>"
        f"<UploadId>{escape(str(upload.id))}</UploadId>"
        "<StorageClass>STANDARD</StorageClass>"
        f"<Initiated>{format_s3_timestamp(upload.created_at)}</Initiated>"
        "</Upload>"
        for upload in page.uploads
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ListMultipartUploadsResult>"
        f"<Bucket>{escape(bucket)}</Bucket>"
        f"{uploads}"
        "</ListMultipartUploadsResult>"
    )


def render_create_multipart_upload(
    bucket: str, key: str, upload_id: uuid.UUID
) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<InitiateMultipartUploadResult>"
        f"<Bucket>{escape(bucket)}</Bucket>"
        f"<Key>{escape(key)}</Key>"
        f"<UploadId>{escape(str(upload_id))}</UploadId>"
        "</InitiateMultipartUploadResult>"
    )


def render_complete_multipart_upload(
    result: object_multipart.CompleteMultipartResult,
) -> str:
    location = f"/s3/{escape(result.bucket)}/{escape(result.key)}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<CompleteMultipartUploadResult>"
        f"<Location>{location}</Location>"
        f"<Bucket>{escape(result.bucket)}</Bucket>"
        f"<Key>{escape(result.key)}</Key>"
        f"<ETag>&quot;{result.etag}&quot;</ETag>"
        "</CompleteMultipartUploadResult>"
    )


def render_copy_object(*, etag: str, last_modified: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<CopyObjectResult>"
        f"<ETag>&quot;{etag}&quot;</ETag>"
        f"<LastModified>{last_modified}</LastModified>"
        "</CopyObjectResult>"
    )


def render_list_multipart_parts(
    bucket: str,
    key: str,
    page: object_multipart.MultipartPartListPage,
) -> str:
    parts = "".join(
        "<Part>"
        f"<PartNumber>{part.part_number}</PartNumber>"
        f"<LastModified>{format_s3_timestamp(part.updated_at)}</LastModified>"
        f"<ETag>&quot;{escape(part.etag)}&quot;</ETag>"
        f"<Size>{part.size_bytes}</Size>"
        "</Part>"
        for part in page.parts
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ListPartsResult>"
        f"<Bucket>{escape(bucket)}</Bucket>"
        f"<Key>{escape(key)}</Key>"
        f"<UploadId>{escape(str(page.upload.id))}</UploadId>"
        f"{parts}"
        "</ListPartsResult>"
    )


def build_object_response_headers(result: GetObjectResult) -> dict[str, str]:
    return {
        "ETag": f'"{result.blob.content_hash.hex()}"',
        "Last-Modified": result.file.updated_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "Content-Length": str(result.blob.size_bytes),
        "Content-Type": result.blob.mimetype or "application/octet-stream",
    }
