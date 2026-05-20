import hashlib

import settings as S
from api.dependencies import UnitOfWorkDep
from api.s3.helpers import (
    extract_user_metadata,
    list_objects_response_cache_key,
    load_signed_user,
    parse_complete_multipart_body,
    parse_copy_source,
    parse_max_keys,
    parse_part_number,
    parse_upload_id,
    spool_request_body,
    stream_boto_body,
)
from api.s3.xml import (
    build_object_response_headers,
    domain_error_response,
    multipart_not_found_response,
    render_complete_multipart_upload,
    render_copy_object,
    render_create_multipart_upload,
    render_list_buckets,
    render_list_multipart_parts,
    render_list_multipart_uploads,
    render_list_objects_v2,
    s3_error_response,
)
from application.gateway import object_mutations
from application.gateway import s3_listing as gateway_listing
from infra.gateway import object_reads
from application.gateway import object_signing
from infra.gateway.object_types import CopyObjectResult
from constants import S3_METADATA_DIRECTIVE_COPY
from domain.exceptions import DomainError, ResourceNotFound
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from infra.cache.hotpath import get_list_objects_response, set_list_objects_response
from ports.entities import User

router = APIRouter()

"""
Proxies S3 requests to the underlying storage_backends.

Path-style routing only (e.g. PUT /{bucket}/{key}). StorageBackend maps to a top-level
Folder; key maps to nested Folders + final File.name. Authentication is SigV4
against AccessKey rows.
"""


@router.get("/")
async def list_buckets(request: Request, uow: UnitOfWorkDep) -> Response:
    try:
        user = load_signed_user(request, uow.session)
        buckets = gateway_listing.list_visible_buckets(uow, user)
    except object_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    body = render_list_buckets(
        owner_id=str(user.id),
        owner_name=user.name,
        buckets=buckets,
    )
    return Response(content=body, status_code=200, media_type="application/xml")


@router.head("/{bucket}")
async def head_bucket(bucket: str, request: Request, uow: UnitOfWorkDep) -> Response:
    try:
        user = load_signed_user(request, uow.session)
        gateway_listing.require_visible_bucket(uow, user, bucket)
    except object_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except ResourceNotFound:
        return s3_error_response("NoSuchBucket", "Storage backend not found", status_code=404)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=200)


@router.get("/{bucket}")
async def list_objects_v2(bucket: str, request: Request, uow: UnitOfWorkDep) -> Response:
    query = request.query_params
    if "uploads" in query:
        try:
            user = load_signed_user(request, uow.session)
            gateway_listing.require_visible_bucket(uow, user, bucket)
            page = object_mutations.list_multipart_uploads(
                uow,
                bucket_name=bucket,
                current_user=user,
            )
        except object_signing.S3SigningError as exc:
            return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
        except ResourceNotFound:
            return s3_error_response("NoSuchBucket", "Storage backend not found", status_code=404)
        except DomainError as exc:
            return domain_error_response(exc)

        return Response(
            content=render_list_multipart_uploads(bucket, page),
            status_code=200,
            media_type="application/xml",
        )

    if query.get("list-type") != "2":
        return s3_error_response(
            "InvalidRequest",
            "Only ListObjectsV2 and ListMultipartUploads are supported for bucket listings",
            status_code=400,
        )

    try:
        user = load_signed_user(request, uow.session)
        max_keys = parse_max_keys(query.get("max-keys"))
        cache_key = list_objects_response_cache_key(
            user=user,
            bucket=bucket,
            prefix=query.get("prefix") or "",
            delimiter=query.get("delimiter") or None,
            max_keys=max_keys,
            continuation_token=query.get("continuation-token") or None,
            start_after=query.get("start-after") or None,
        )
        cached_body = get_list_objects_response(cache_key)
        if cached_body is not None:
            return Response(
                content=cached_body,
                status_code=200,
                media_type="application/xml",
            )
        page = gateway_listing.list_objects_v2(
            uow,
            user=user,
            bucket_name=bucket,
            prefix=query.get("prefix") or "",
            delimiter=query.get("delimiter") or None,
            max_keys=max_keys,
            continuation_token=query.get("continuation-token") or None,
            start_after=query.get("start-after") or None,
        )
    except object_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except ResourceNotFound:
        return s3_error_response("NoSuchBucket", "Storage backend not found", status_code=404)
    except DomainError as exc:
        return domain_error_response(exc)

    body = render_list_objects_v2(page)
    set_list_objects_response(
        cache_key,
        body,
        ttl_seconds=S.S3_LIST_OBJECTS_CACHE_TTL_SECONDS,
    )
    return Response(
        content=body,
        status_code=200,
        media_type="application/xml",
    )


@router.post("/{bucket}/{key:path}")
async def multipart_post(
    bucket: str, key: str, request: Request, uow: UnitOfWorkDep
) -> Response:
    query = request.query_params
    try:
        user = load_signed_user(request, uow.session)
        if "uploads" in query:
            object_signing.verify_empty_payload_hash(request)
            upload = object_mutations.create_multipart_upload(
                uow,
                bucket_name=bucket,
                key=key,
                ingest_meta=extract_user_metadata(request),
                current_user=user,
            )
            return Response(
                content=render_create_multipart_upload(bucket, key, upload.id),
                status_code=200,
                media_type="application/xml",
            )
        upload_id = parse_upload_id(query.get("uploadId"))
        body = await request.body()
        object_signing.verify_payload_hash(request, hashlib.sha256(body).digest())
        parts = parse_complete_multipart_body(body)
        result = object_mutations.complete_multipart_upload(
            uow,
            upload_id=upload_id,
            bucket_name=bucket,
            key=key,
            requested_parts=parts,
            current_user=user,
        )
    except object_signing.S3SigningError as exc:
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


@router.put("/{bucket}/{key:path}")
async def put_object(
    bucket: str, key: str, request: Request, uow: UnitOfWorkDep
) -> Response:
    try:
        user = load_signed_user(request, uow.session)

        upload_id_value = request.query_params.get("uploadId")
        if upload_id_value is not None:
            upload_id = parse_upload_id(upload_id_value)
            spooled = await spool_request_body(request)
            object_signing.verify_payload_hash(request, spooled.content_hash)
            part = object_mutations.upload_part(
                uow,
                upload_id=upload_id,
                bucket_name=bucket,
                key=key,
                part_number=parse_part_number(request.query_params.get("partNumber")),
                body=spooled.body,
                content_hash=spooled.content_hash,
                content_md5=spooled.content_md5,
                size_bytes=spooled.size_bytes,
                current_user=user,
            )
            return Response(status_code=200, headers={"ETag": f'"{part.etag}"'})

        copy_source = request.headers.get("x-amz-copy-source")
        if copy_source is not None:
            object_signing.verify_empty_payload_hash(request)
            response, _result = _handle_copy_object(
                uow=uow,
                request=request,
                user=user,
                dest_bucket=bucket,
                dest_key=key,
                copy_source=copy_source,
            )
            return response

        spooled = await spool_request_body(request)
        object_signing.verify_payload_hash(request, spooled.content_hash)
        result = object_mutations.put_object(
            uow,
            bucket_name=bucket,
            key=key,
            body=spooled.body,
            content_hash=spooled.content_hash,
            size_bytes=spooled.size_bytes,
            ingest_meta=extract_user_metadata(request),
            current_user=user,
            allow_overwrite=request.headers.get("x-relic-if-none-match") != "*",
        )
    except object_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=200, headers={"ETag": f'"{result.etag}"'})


def _handle_copy_object(
    *,
    uow,
    request: Request,
    user: User,
    dest_bucket: str,
    dest_key: str,
    copy_source: str,
) -> tuple[Response, CopyObjectResult]:
    source_bucket, source_key = parse_copy_source(copy_source)
    metadata_directive = (
        request.headers.get("x-amz-metadata-directive") or S3_METADATA_DIRECTIVE_COPY
    ).upper()
    result = object_mutations.copy_object(
        uow,
        source_bucket=source_bucket,
        source_key=source_key,
        dest_bucket=dest_bucket,
        dest_key=dest_key,
        ingest_meta=extract_user_metadata(request),
        metadata_directive=metadata_directive,
        current_user=user,
    )
    last_modified = result.file.updated_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = render_copy_object(etag=result.etag, last_modified=last_modified)
    return (
        Response(
            content=body,
            status_code=200,
            media_type="application/xml",
            headers={"ETag": f'"{result.etag}"'},
        ),
        result,
    )


@router.head("/{bucket}/{key:path}")
async def head_object(
    bucket: str, key: str, request: Request, uow: UnitOfWorkDep
) -> Response:
    try:
        user = load_signed_user(request, uow.session)
        result = object_reads.head_object(
            uow.session,
            bucket_name=bucket,
            key=key,
            current_user=user,
        )
        object_mutations.touch_blob_access(uow, result.blob)
    except object_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=200, headers=build_object_response_headers(result))


@router.get("/{bucket}/{key:path}")
async def get_object(
    bucket: str, key: str, request: Request, uow: UnitOfWorkDep
) -> Response:
    try:
        user = load_signed_user(request, uow.session)
        upload_id_value = request.query_params.get("uploadId")
        if upload_id_value is not None:
            page = object_mutations.list_multipart_parts(
                uow,
                upload_id=parse_upload_id(upload_id_value),
                bucket_name=bucket,
                key=key,
                current_user=user,
            )
            return Response(
                content=render_list_multipart_parts(bucket, key, page),
                status_code=200,
                media_type="application/xml",
            )
        object_bytes = object_reads.get_object_bytes(
            uow.session,
            storage=uow.storage,
            bucket_name=bucket,
            key=key,
            range_header=request.headers.get("range"),
            current_user=user,
        )
        result = object_bytes.result
        boto_response = object_bytes.boto_response
        object_mutations.touch_blob_access(uow, result.blob)
    except object_signing.S3SigningError as exc:
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


@router.delete("/{bucket}/{key:path}")
async def delete_object(
    bucket: str, key: str, request: Request, uow: UnitOfWorkDep
) -> Response:
    try:
        user = load_signed_user(request, uow.session)
        upload_id_value = request.query_params.get("uploadId")
        if upload_id_value is not None:
            object_signing.verify_empty_payload_hash(request)
            object_mutations.abort_multipart_upload(
                uow,
                upload_id=parse_upload_id(upload_id_value),
                bucket_name=bucket,
                key=key,
                current_user=user,
            )
            return Response(status_code=204)

        object_signing.verify_empty_payload_hash(request)
        object_mutations.delete_object(
            uow,
            bucket_name=bucket,
            key=key,
            current_user=user,
        )
    except object_signing.S3SigningError as exc:
        return s3_error_response(exc.code, exc.message, status_code=exc.status_code)
    except ResourceNotFound as exc:
        return multipart_not_found_response(exc)
    except DomainError as exc:
        return domain_error_response(exc)

    return Response(status_code=204)
