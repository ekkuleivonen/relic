"""Opaque per-file metadata owned by external consumers.

Relic does not impose a schema on ``File.meta``. Upload paths pass through
caller-supplied JSON; consumers patch fields via the files API as needed.

Gateway HEAD/GET expose all non-standard S3 fields in a single
``x-amz-meta-relic-meta`` JSON header (see ``build_relic_meta_envelope``).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from constants import S3_RELIC_META_HEADER, S3_USER_METADATA_MAX_BYTES
from domain.exceptions import BadRequestError
from utils.logging import get_logger

log = get_logger(__name__)


def normalize_ingest_meta(user_meta: dict[str, Any] | None) -> dict[str, Any]:
    if user_meta is None:
        return {}
    if not isinstance(user_meta, dict):
        raise TypeError("meta must be an object")
    return dict(user_meta)


def patch_meta(existing: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise TypeError("patch must be an object")
    merged = dict(existing or {})
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = patch_meta(merged[key], value)
        else:
            merged[key] = value
    return merged


def is_reserved_user_metadata_key(name: str) -> bool:
    normalized = name.strip().lower().removeprefix("x-amz-meta-")
    return normalized == "relic-user" or normalized.startswith("relic-")


def validate_user_metadata_ingest(meta: dict[str, str]) -> None:
    for key in meta:
        if is_reserved_user_metadata_key(key):
            raise BadRequestError(f"Metadata name is reserved: {key.strip().lower()}")


def build_relic_meta_envelope(
    *,
    file_id: uuid.UUID,
    blob_id: uuid.UUID,
    folder_id: uuid.UUID,
    meta: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "file_id": str(file_id),
        "blob_id": str(blob_id),
        "folder_id": str(folder_id),
        "meta": dict(meta or {}),
    }


def gateway_user_metadata_headers(
    *,
    file_id: uuid.UUID,
    blob_id: uuid.UUID,
    folder_id: uuid.UUID,
    meta: dict[str, Any] | None,
) -> dict[str, str]:
    """Build the single Relic metadata header for gateway HEAD/GET responses."""
    envelope = build_relic_meta_envelope(
        file_id=file_id,
        blob_id=blob_id,
        folder_id=folder_id,
        meta=meta,
    )
    meta_json = json.dumps(envelope, separators=(",", ":"), sort_keys=True, default=str)
    encoded_size = len(S3_RELIC_META_HEADER.encode("utf-8")) + len(meta_json.encode("utf-8"))
    if encoded_size > S3_USER_METADATA_MAX_BYTES:
        log.warning(
            "s3_metadata_json_header_dropped",
            bytes=len(meta_json.encode("utf-8")),
            budget=S3_USER_METADATA_MAX_BYTES,
        )
        return {}
    return {S3_RELIC_META_HEADER: meta_json}
