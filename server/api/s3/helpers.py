"""S3 gateway request helpers (auth, spooling, parsing)."""

import hashlib
import tempfile
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import BinaryIO
from urllib.parse import unquote

import settings as S
from constants import S3_LISTING_DEFAULT_MAX_KEYS, S3_USER_BINDING_HEADER
from domain.exceptions import BadRequestError
from fastapi import Request
from infra.db.engine import DbSession
from infra.db.models import User
from application.gateway import object_multipart
from application.gateway import object_signing
from infra.cache.hotpath import begin_request, get_or_set_request


@dataclass(frozen=True)
class SpoolResult:
    body: BinaryIO
    content_hash: bytes
    content_md5: bytes
    size_bytes: int


def load_signed_user(request: Request, db: DbSession) -> User:
    if not getattr(request.state, "folder_hotpath_cache_started", False):
        begin_request(db)
        request.state.folder_hotpath_cache_started = True

    verified = get_or_set_request(
        db,
        "verified_request",
        lambda: object_signing.verify_request(request, db),
    )
    user = get_or_set_request(
        db,
        f"signed_user:{verified.user_id}",
        lambda: db.get(User, verified.user_id),
    )
    if user is None:
        raise object_signing.S3SigningError(
            "InvalidAccessKeyId",
            "The signed user no longer exists",
        )
    return user


def list_objects_response_cache_key(
    *,
    user: User,
    bucket: str,
    prefix: str,
    delimiter: str | None,
    max_keys: int,
    continuation_token: str | None,
    start_after: str | None,
) -> tuple:
    return (
        str(user.id),
        int(user.role),
        bucket,
        prefix,
        delimiter or "",
        max_keys,
        continuation_token or "",
        start_after or "",
    )


def parse_max_keys(value: str | None) -> int:
    if value in (None, ""):
        return S3_LISTING_DEFAULT_MAX_KEYS
    try:
        return int(value)
    except ValueError as exc:
        raise BadRequestError("max-keys must be an integer") from exc


def parse_copy_source(value: str) -> tuple[str, str]:
    decoded = unquote(value).lstrip("/")
    if "/" not in decoded:
        raise BadRequestError("x-amz-copy-source must be '/{bucket}/{key}'")
    bucket, key = decoded.split("/", 1)
    if not bucket or not key:
        raise BadRequestError("x-amz-copy-source must be '/{bucket}/{key}'")
    return bucket, key


async def spool_request_body(request: Request) -> SpoolResult:
    digest = hashlib.sha256()
    try:
        md5_digest = hashlib.md5(usedforsecurity=False)
    except TypeError:
        md5_digest = hashlib.md5()
    size_bytes = 0
    body = tempfile.SpooledTemporaryFile(max_size=S.UPLOAD_SPOOL_MAX_MEMORY_BYTES)

    async for chunk in request.stream():
        if not chunk:
            continue
        size_bytes += len(chunk)
        digest.update(chunk)
        md5_digest.update(chunk)
        body.write(chunk)

    body.seek(0)
    return SpoolResult(
        body=body,
        content_hash=digest.digest(),
        content_md5=md5_digest.digest(),
        size_bytes=size_bytes,
    )


def extract_user_metadata(request: Request) -> dict[str, str]:
    prefix = "x-amz-meta-"
    return {
        header_name.removeprefix(prefix): header_value
        for header_name, header_value in request.headers.items()
        if header_name.startswith(prefix)
        and header_name != S3_USER_BINDING_HEADER
    }


def parse_complete_multipart_body(
    body: bytes,
) -> list[object_multipart.CompleteMultipartPart]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise BadRequestError("CompleteMultipartUpload body must be valid XML") from exc

    parts: list[object_multipart.CompleteMultipartPart] = []
    for part in root.iter():
        if _local_name(part.tag) != "Part":
            continue
        part_number_text = _child_text(part, "PartNumber")
        if part_number_text is None:
            raise BadRequestError("Each multipart completion part needs PartNumber")
        try:
            part_number = int(part_number_text)
        except ValueError as exc:
            raise BadRequestError("PartNumber must be an integer") from exc
        parts.append(
            object_multipart.CompleteMultipartPart(
                part_number=part_number,
                etag=_child_text(part, "ETag"),
            )
        )
    return parts


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


def stream_boto_body(body):
    chunk_size = 64 * 1024
    while True:
        chunk = body.read(chunk_size)
        if not chunk:
            break
        yield chunk


def _child_text(element: ET.Element, wanted_name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == wanted_name:
            return child.text
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
