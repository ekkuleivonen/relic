"""Sniff blob mimetype and extension from bytes and filename at ingest time."""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from constants import FILE_INFO_PREFIX_BYTES


def extension_from_filename(filename: str) -> str:
    return PurePosixPath(filename).suffix.removeprefix(".").lower()


def detect_mime_type(*, prefix: bytes, filename: str) -> str:
    signature = detect_signature_mime_type(prefix)
    if signature:
        return signature
    lower_name = filename.lower()
    if lower_name.endswith(".parquet"):
        return "application/vnd.apache.parquet"
    if lower_name.endswith((".htm", ".html")):
        return "text/html"
    if lower_name.endswith(".xhtml"):
        return "application/xhtml+xml"
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def detect_signature_mime_type(prefix: bytes) -> str | None:
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"PK\x03\x04"):
        return "application/zip"
    if prefix.startswith(b"\x1f\x8b"):
        return "application/gzip"
    if prefix.startswith(b"PAR1"):
        return "application/vnd.apache.parquet"
    if prefix.startswith(b"SQLite format 3\x00"):
        return "application/vnd.sqlite3"
    head = prefix.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return "text/html"
    return None


def read_body_prefix(body, *, max_bytes: int | None = None) -> bytes:
    limit = max_bytes if max_bytes is not None else FILE_INFO_PREFIX_BYTES
    if limit <= 0:
        return b""
    position = body.tell()
    try:
        body.seek(0)
        return body.read(limit)
    finally:
        body.seek(position)


def sniff_blob_attributes(
    *,
    body,
    filename: str,
    size_bytes: int,
) -> tuple[str, str, int]:
    prefix = read_body_prefix(body)
    mimetype = detect_mime_type(prefix=prefix, filename=filename)
    extension = extension_from_filename(filename)
    return mimetype, extension, size_bytes
