import hashlib
import tempfile
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import BinaryIO
from urllib.parse import unquote
from xml.sax.saxutils import escape

import settings as S
from database import DbSession
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from managers.exceptions import (
    BadRequestError,
    ConflictError,
    DomainError,
    PermissionDenied,
    ResourceNotFound,
)
from models import User
from services.event_context import context_from_headers
from services import objects as object_service
from services import s3_listing
from services import s3_multipart
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
async def list_buckets(request: Request, db: DbSession) -> Response:
    """
    GET / -> ListBuckets

    Returns top-level folders the authenticated principal can see.
    XML response: <ListAllMyBucketsResult>...</ListAllMyBucketsResult>
    """
    try:
        user = load_signed_user(request, db)
        buckets = s3_listing.list_visible_buckets(db, user)
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    owner_id = escape(str(user.id))
    bucket_xml = "".join(
        "<Bucket>"
        f"<Name>{escape(bucket.name)}</Name>"
        f"<CreationDate>{format_s3_timestamp(bucket.created_at)}</CreationDate>"
        "</Bucket>"
        for bucket in buckets
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ListAllMyBucketsResult>"
        "<Owner>"
        f"<ID>{owner_id}</ID>"
        f"<DisplayName>{escape(user.name)}</DisplayName>"
        "</Owner>"
        f"<Buckets>{bucket_xml}</Buckets>"
        "</ListAllMyBucketsResult>"
    )
    return Response(content=body, status_code=200, media_type="application/xml")


# -----------------------------------------------------------------------------
# Bucket-level operations
# -----------------------------------------------------------------------------


@router.head("/{bucket}")
async def head_bucket(bucket: str, request: Request, db: DbSession) -> Response:
    """
    HEAD /{bucket} -> HeadBucket

    Existence + access check for a top-level folder. 200 if visible to caller,
    404 otherwise. Many SDK clients call this before any other operation.
    """
    try:
        user = load_signed_user(request, db)
        s3_listing.require_visible_bucket(db, user, bucket)
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except ResourceNotFound:
        return s3_error_response("NoSuchBucket", "Bucket not found", status_code=404)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=200)


@router.get("/{bucket}")
async def list_objects_v2(bucket: str, request: Request, db: DbSession) -> Response:
    """
    GET /{bucket}?list-type=2 -> ListObjectsV2

    Lists Files within the folder, with prefix/delimiter support to expose
    nested folders as "common prefixes". Supports pagination via
    continuation-token. This is the workhorse for any client that browses.

    Query params we care about: list-type, prefix, delimiter, max-keys,
    continuation-token, start-after.
    """
    query = request.query_params
    if query.get("list-type") != "2":
        return s3_error_response(
            "InvalidRequest",
            "Only ListObjectsV2 is supported for bucket listings",
            status_code=400,
        )

    try:
        user = load_signed_user(request, db)
        page = s3_listing.list_objects_v2(
            db,
            user,
            bucket_name=bucket,
            prefix=query.get("prefix") or "",
            delimiter=query.get("delimiter") or None,
            max_keys=parse_max_keys(query.get("max-keys")),
            continuation_token=query.get("continuation-token") or None,
            start_after=query.get("start-after") or None,
        )
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except ResourceNotFound:
        return s3_error_response("NoSuchBucket", "Bucket not found", status_code=404)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(
        content=render_list_objects_v2(page),
        status_code=200,
        media_type="application/xml",
    )


# -----------------------------------------------------------------------------
# Object-level operations
# -----------------------------------------------------------------------------


def load_signed_user(request: Request, db: DbSession) -> User:
    verified = s3_signing.verify_signed_request(request)
    user = db.get(User, verified.user_id)
    if user is None:
        raise s3_signing.S3SigningError(
            "InvalidAccessKeyId",
            "The signed user no longer exists",
        )
    return user


def parse_max_keys(value: str | None) -> int:
    if value in (None, ""):
        return s3_listing.DEFAULT_MAX_KEYS
    try:
        return int(value)
    except ValueError as exc:
        raise BadRequestError("max-keys must be an integer") from exc


def format_s3_timestamp(value) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def render_list_objects_v2(page: s3_listing.ListObjectsV2Page) -> str:
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
    body = (
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
    return body


@router.post("/{bucket}/{key:path}")
async def multipart_post(
    bucket: str, key: str, request: Request, db: DbSession
) -> Response:
    query = request.query_params
    try:
        user = load_signed_user(request, db)
        if "uploads" in query:
            upload = s3_multipart.create_multipart_upload(
                db,
                bucket_name=bucket,
                key=key,
                ingest_meta=extract_user_metadata(request),
                current_user=user,
                event_context=context_from_headers(
                    request.headers,
                    actor_user_id=user.id,
                ),
            )
            return Response(
                content=render_create_multipart_upload(bucket, key, upload.id),
                status_code=200,
                media_type="application/xml",
            )
        upload_id = parse_upload_id(query.get("uploadId"))
        parts = parse_complete_multipart_body(await request.body())
        result = s3_multipart.complete_multipart_upload(
            db,
            upload_id=upload_id,
            bucket_name=bucket,
            key=key,
            requested_parts=parts,
            current_user=user,
            event_context=context_from_headers(
                request.headers,
                actor_user_id=user.id,
            ),
        )
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except ResourceNotFound as exc:
        return multipart_not_found_response(exc)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(
        content=render_complete_multipart_upload(result),
        status_code=200,
        media_type="application/xml",
        headers={"ETag": f'"{result.etag}"'},
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
    result: s3_multipart.CompleteMultipartResult,
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


def parse_complete_multipart_body(body: bytes) -> list[s3_multipart.CompleteMultipartPart]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise BadRequestError("CompleteMultipartUpload body must be valid XML") from exc

    parts: list[s3_multipart.CompleteMultipartPart] = []
    for part in root.iter():
        if local_name(part.tag) != "Part":
            continue
        part_number_text = child_text(part, "PartNumber")
        if part_number_text is None:
            raise BadRequestError("Each multipart completion part needs PartNumber")
        try:
            part_number = int(part_number_text)
        except ValueError as exc:
            raise BadRequestError("PartNumber must be an integer") from exc
        parts.append(
            s3_multipart.CompleteMultipartPart(
                part_number=part_number,
                etag=child_text(part, "ETag"),
            )
        )
    return parts


def child_text(element: ET.Element, wanted_name: str) -> str | None:
    for child in element:
        if local_name(child.tag) == wanted_name:
            return child.text
    return None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_upload_id(value: str | None) -> uuid.UUID:
    if not value:
        raise BadRequestError("uploadId is required")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise BadRequestError("uploadId must be a UUID") from exc


def parse_part_number(value: str | None) -> int:
    if not value:
        raise BadRequestError("partNumber is required")
    try:
        return int(value)
    except ValueError as exc:
        raise BadRequestError("partNumber must be an integer") from exc


def multipart_not_found_response(exc: ResourceNotFound) -> Response:
    message = str(exc.detail)
    if "Multipart upload" in message:
        return s3_error_response("NoSuchUpload", message, status_code=404)
    return s3_error_response("NoSuchBucket", message, status_code=404)


@router.put("/{bucket}/{key:path}")
async def put_object(
    bucket: str, key: str, request: Request, db: DbSession
) -> Response:
    """
    PUT /{bucket}/{key} -> PutObject (or CopyObject when x-amz-copy-source is set).

    Verifies the SigV4 presigned URL, loads the bound user, and dispatches to
    the appropriate object service operation. The gateway has no UI fast-path:
    every request goes through verify -> permission check -> service call.
    """
    try:
        user = load_signed_user(request, db)

        upload_id_value = request.query_params.get("uploadId")
        if upload_id_value is not None:
            upload_id = parse_upload_id(upload_id_value)
            spooled = await spool_request_body(request)
            part = s3_multipart.upload_part(
                db,
                upload_id=upload_id,
                bucket_name=bucket,
                key=key,
                part_number=parse_part_number(request.query_params.get("partNumber")),
                body=spooled.body,
                content_hash=spooled.content_hash,
                size_bytes=spooled.size_bytes,
                current_user=user,
            )
            return Response(status_code=200, headers={"ETag": f'"{part.etag}"'})

        copy_source = request.headers.get("x-amz-copy-source")
        if copy_source is not None:
            response, _result = handle_copy_object(
                db=db,
                request=request,
                user=user,
                dest_bucket=bucket,
                dest_key=key,
                copy_source=copy_source,
            )
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
            allow_overwrite=request.headers.get("x-relic-if-none-match") != "*",
            event_context=context_from_headers(
                request.headers,
                actor_user_id=user.id,
            ),
        )
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
) -> tuple[Response, object_service.CopyObjectResult]:
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
        event_context=context_from_headers(
            request.headers,
            actor_user_id=user.id,
        ),
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
        result,
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
async def head_object(
    bucket: str, key: str, request: Request, db: DbSession
) -> Response:
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
        result = object_service.head_object(
            db,
            bucket_name=bucket,
            key=key,
            current_user=user,
        )
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=200, headers=build_object_response_headers(result))


@router.get("/{bucket}/{key:path}")
async def get_object(
    bucket: str, key: str, request: Request, db: DbSession
) -> Response:
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
        object_bytes = object_service.get_object_bytes(
            db,
            bucket_name=bucket,
            key=key,
            range_header=request.headers.get("range"),
            current_user=user,
        )
        result = object_bytes.result
        boto_response = object_bytes.boto_response
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


def build_object_response_headers(
    result: object_service.GetObjectResult,
) -> dict[str, str]:
    file_meta = result.file.meta or {}
    headers: dict[str, str] = {
        "ETag": f'"{result.blob.content_hash.hex()}"',
        "Last-Modified": result.file.updated_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "Content-Length": str(result.blob.size_bytes),
    }
    if file_meta.get("mimetype"):
        headers["Content-Type"] = file_meta["mimetype"]
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
async def delete_object(
    bucket: str, key: str, request: Request, db: DbSession
) -> Response:
    """
    DELETE /{bucket}/{key} -> DeleteObject. Idempotent per S3 contract: a
    missing key still returns 204.
    """
    try:
        user = load_signed_user(request, db)
        upload_id_value = request.query_params.get("uploadId")
        if upload_id_value is not None:
            s3_multipart.abort_multipart_upload(
                db,
                upload_id=parse_upload_id(upload_id_value),
                bucket_name=bucket,
                key=key,
                current_user=user,
            )
            return Response(status_code=204)

        object_service.delete_object(
            db,
            bucket_name=bucket,
            key=key,
            current_user=user,
            event_context=context_from_headers(
                request.headers,
                actor_user_id=user.id,
            ),
        )
    except s3_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except ResourceNotFound as exc:
        return multipart_not_found_response(exc)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=204)


