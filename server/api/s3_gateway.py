import hashlib
import tempfile
import uuid
from dataclasses import dataclass
from typing import BinaryIO
from urllib.parse import unquote
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

import settings as S
from database import DbSession
from managers.exceptions import (
    BadRequestError,
    ConflictError,
    DomainError,
    PermissionDenied,
    ResourceNotFound,
)
from models import User
from services import objects as object_service
from services import parser_queue
from services import s3_signing

router = APIRouter()


@dataclass(frozen=True)
class SpoolResult:
    body: BinaryIO
    content_hash: bytes
    size_bytes: int

"""
Proxies S3 requests to the underlying buckets.

Endpoints in this router show the current S3 API compatibility.

Path-style routing only for now (e.g. PUT /{bucket}/{key}). Virtual-hosted-style
(bucket.host/key) can be added later via middleware that rewrites Host header
into a path prefix before these handlers see the request.

Bucket maps to a top-level Folder; key (slashes included) maps to nested
Folders + final File.name. Authentication is SigV4 against AccessKey rows.
"""


# -----------------------------------------------------------------------------
# Service-level operations (no bucket in path)
# -----------------------------------------------------------------------------


@router.get("/")
async def list_buckets(request: Request) -> Response:
    """
    GET / -> ListBuckets

    Returns top-level folders the authenticated principal can see.
    XML response: <ListAllMyBucketsResult>...</ListAllMyBucketsResult>
    """
    raise NotImplementedError


# -----------------------------------------------------------------------------
# Bucket-level operations
# -----------------------------------------------------------------------------


@router.head("/{bucket}")
async def head_bucket(bucket: str, request: Request) -> Response:
    """
    HEAD /{bucket} -> HeadBucket

    Existence + access check for a top-level folder. 200 if visible to caller,
    404 otherwise. Many SDK clients call this before any other operation.
    """
    raise NotImplementedError


@router.get("/{bucket}")
async def list_objects_v2(bucket: str, request: Request) -> Response:
    """
    GET /{bucket}?list-type=2 -> ListObjectsV2

    Lists Files within the folder, with prefix/delimiter support to expose
    nested folders as "common prefixes". Supports pagination via
    continuation-token. This is the workhorse for any client that browses.

    Query params we care about: list-type, prefix, delimiter, max-keys,
    continuation-token, start-after.
    """
    raise NotImplementedError


# -----------------------------------------------------------------------------
# Object-level operations
# -----------------------------------------------------------------------------


@router.put("/{bucket}/{key:path}")
async def put_object(bucket: str, key: str, request: Request, db: DbSession) -> Response:
    """
    PUT /{bucket}/{key} -> PutObject (or CopyObject when x-amz-copy-source is set).

    Verifies the SigV4 presigned URL, loads the bound user, and dispatches to
    the appropriate object service operation. The gateway has no UI fast-path:
    every request goes through verify -> permission check -> service call.
    """
    try:
        verified = s3_signing.verify_signed_request(request)
        user = db.get(User, verified.user_id)
        if user is None:
            return s3_error_response(
                "InvalidAccessKeyId",
                "The signed user no longer exists",
                status_code=403,
            )

        copy_source = request.headers.get("x-amz-copy-source")
        if copy_source is not None:
            response, file_id = handle_copy_object(
                db=db,
                request=request,
                user=user,
                dest_bucket=bucket,
                dest_key=key,
                copy_source=copy_source,
            )
            await parser_queue.enqueue_parse_file_best_effort(file_id)
            return response

        spooled = await spool_request_body(request)
        result = object_service.put_object(
            db,
            bucket_name=bucket,
            key=key,
            body=spooled.body,
            content_hash=spooled.content_hash,
            size_bytes=spooled.size_bytes,
            ingest_meta=extract_user_metadata(request),
            current_user=user,
        )
        await parser_queue.enqueue_parse_file_best_effort(result.file.id)
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=200, headers={"ETag": f'"{result.etag}"'})


def handle_copy_object(
    *,
    db,
    request: Request,
    user: User,
    dest_bucket: str,
    dest_key: str,
    copy_source: str,
) -> tuple[Response, uuid.UUID]:
    source_bucket, source_key = parse_copy_source(copy_source)
    metadata_directive = (
        request.headers.get("x-amz-metadata-directive")
        or object_service.METADATA_DIRECTIVE_COPY
    ).upper()
    result = object_service.copy_object(
        db,
        source_bucket=source_bucket,
        source_key=source_key,
        dest_bucket=dest_bucket,
        dest_key=dest_key,
        ingest_meta=extract_user_metadata(request),
        metadata_directive=metadata_directive,
        current_user=user,
    )
    last_modified = result.file.updated_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<CopyObjectResult>"
        f"<ETag>&quot;{result.etag}&quot;</ETag>"
        f"<LastModified>{last_modified}</LastModified>"
        "</CopyObjectResult>"
    )
    return (
        Response(
            content=body,
            status_code=200,
            media_type="application/xml",
            headers={"ETag": f'"{result.etag}"'},
        ),
        result.file.id,
    )


def parse_copy_source(value: str) -> tuple[str, str]:
    """
    S3 sends x-amz-copy-source as either '/{bucket}/{key}' or '{bucket}/{key}'.
    The key may be URL-encoded.
    """
    decoded = unquote(value).lstrip("/")
    if "/" not in decoded:
        raise BadRequestError("x-amz-copy-source must be '/{bucket}/{key}'")
    bucket, key = decoded.split("/", 1)
    if not bucket or not key:
        raise BadRequestError("x-amz-copy-source must be '/{bucket}/{key}'")
    return bucket, key


async def spool_request_body(request: Request) -> SpoolResult:
    digest = hashlib.sha256()
    size_bytes = 0
    body = tempfile.SpooledTemporaryFile(max_size=S.UPLOAD_SPOOL_MAX_MEMORY_BYTES)

    async for chunk in request.stream():
        if not chunk:
            continue
        size_bytes += len(chunk)
        digest.update(chunk)
        body.write(chunk)

    body.seek(0)
    return SpoolResult(
        body=body,
        content_hash=digest.digest(),
        size_bytes=size_bytes,
    )


def extract_user_metadata(request: Request) -> dict[str, str]:
    prefix = "x-amz-meta-"
    return {
        header_name.removeprefix(prefix): header_value
        for header_name, header_value in request.headers.items()
        if header_name.startswith(prefix)
        and header_name != s3_signing.USER_BINDING_HEADER
    }


def domain_error_response(exc: DomainError) -> Response:
    if isinstance(exc, ConflictError):
        return s3_error_response("Conflict", str(exc.detail), status_code=409)
    if isinstance(exc, BadRequestError):
        return s3_error_response("InvalidRequest", str(exc.detail), status_code=400)
    if isinstance(exc, ResourceNotFound):
        return s3_error_response("NoSuchKey", str(exc.detail), status_code=404)
    if isinstance(exc, PermissionDenied):
        return s3_error_response("AccessDenied", str(exc.detail), status_code=403)
    return s3_error_response("AccessDenied", "Access denied", status_code=403)


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


@router.head("/{bucket}/{key:path}")
async def head_object(bucket: str, key: str, request: Request, db: DbSession) -> Response:
    """
    HEAD /{bucket}/{key} -> HeadObject. Same shape as GET, no body.
    """
    try:
        verified = s3_signing.verify_signed_request(request)
        user = db.get(User, verified.user_id)
        if user is None:
            return s3_error_response(
                "InvalidAccessKeyId",
                "The signed user no longer exists",
                status_code=403,
            )
        result = object_service.get_object(
            db, bucket_name=bucket, key=key, current_user=user
        )
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=200, headers=build_object_response_headers(result))


@router.get("/{bucket}/{key:path}")
async def get_object(bucket: str, key: str, request: Request, db: DbSession) -> Response:
    """
    GET /{bucket}/{key} -> GetObject. Streams bytes from the underlying bucket.
    """
    try:
        verified = s3_signing.verify_signed_request(request)
        user = db.get(User, verified.user_id)
        if user is None:
            return s3_error_response(
                "InvalidAccessKeyId",
                "The signed user no longer exists",
                status_code=403,
            )
        result = object_service.get_object(
            db, bucket_name=bucket, key=key, current_user=user
        )
        boto_response = object_service.fetch_blob_bytes(
            bucket=result.bucket,
            bucket_key=result.blob.bucket_key,
            range_header=request.headers.get("range"),
        )
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    headers = build_object_response_headers(result)
    if "ContentRange" in boto_response:
        headers["Content-Range"] = boto_response["ContentRange"]
    if "ContentLength" in boto_response:
        headers["Content-Length"] = str(boto_response["ContentLength"])

    body = boto_response["Body"]
    status_code = 206 if "ContentRange" in boto_response else 200
    return StreamingResponse(
        stream_boto_body(body),
        status_code=status_code,
        headers=headers,
        media_type=headers.get("Content-Type") or "application/octet-stream",
    )


def build_object_response_headers(result: object_service.GetObjectResult) -> dict[str, str]:
    file_meta = (result.file.parser_meta or {}).get("file", {})
    headers: dict[str, str] = {
        "ETag": f'"{result.blob.content_hash.hex()}"',
        "Last-Modified": result.file.updated_at.strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        ),
        "Content-Length": str(result.blob.size_bytes),
    }
    if file_meta.get("mime_type"):
        headers["Content-Type"] = file_meta["mime_type"]
    else:
        headers["Content-Type"] = "application/octet-stream"
    return headers


def stream_boto_body(body):
    """Yield chunks from a boto3 StreamingBody so FastAPI can stream them."""
    chunk_size = 64 * 1024
    while True:
        chunk = body.read(chunk_size)
        if not chunk:
            break
        yield chunk


@router.delete("/{bucket}/{key:path}")
async def delete_object(bucket: str, key: str, request: Request, db: DbSession) -> Response:
    """
    DELETE /{bucket}/{key} -> DeleteObject. Idempotent per S3 contract: a
    missing key still returns 204.
    """
    try:
        verified = s3_signing.verify_signed_request(request)
        user = db.get(User, verified.user_id)
        if user is None:
            return s3_error_response(
                "InvalidAccessKeyId",
                "The signed user no longer exists",
                status_code=403,
            )
        object_service.delete_object(
            db, bucket_name=bucket, key=key, current_user=user
        )
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=204)


# -----------------------------------------------------------------------------
# Multipart upload (deferred - uncomment when first large file shows up)
# -----------------------------------------------------------------------------
#
# Clients (boto3, aws-cli) auto-switch to multipart for files over a threshold
# (default 8MB for boto3). Until then they use plain PutObject. We can ship
# without these for a while if we cap accepted size or document the limitation.
#
# @router.post("/{bucket}/{key:path}")  # ?uploads
# async def create_multipart_upload(...): ...
#
# @router.put("/{bucket}/{key:path}")  # ?partNumber=N&uploadId=...
# async def upload_part(...): ...
#
# @router.post("/{bucket}/{key:path}")  # ?uploadId=...
# async def complete_multipart_upload(...): ...
#
# @router.delete("/{bucket}/{key:path}")  # ?uploadId=...
# async def abort_multipart_upload(...): ...
