"""Opaque per-file metadata owned by external consumers.

Pithosys does not impose a schema on ``File.meta``. Upload paths pass through
caller-supplied JSON; consumers patch fields via the files API as needed.

Gateway HEAD/GET expose Pithosys-specific fields as ``x-amz-meta-pithosys-*`` headers:
lineage identifiers as flat headers and consumer ``File.meta`` as JSON in
``x-amz-meta-pithosys-meta``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from constants import (
    S3_PITHOSYS_BLOB_ID_HEADER,
    S3_PITHOSYS_FILE_ID_HEADER,
    S3_PITHOSYS_FOLDER_ID_HEADER,
    S3_PITHOSYS_META_HEADER,
    S3_USER_METADATA_MAX_BYTES,
)
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
    return normalized == "pithosys-user" or normalized.startswith("pithosys-")


def validate_user_metadata_ingest(meta: dict[str, str]) -> None:
    for key in meta:
        if is_reserved_user_metadata_key(key):
            raise BadRequestError(f"Metadata name is reserved: {key.strip().lower()}")


def _metadata_header_size(name: str, value: str) -> int:
    return len(name.encode("utf-8")) + len(value.encode("utf-8"))


def _try_add_metadata_header(
    headers: dict[str, str],
    *,
    budget: int,
    name: str,
    value: str,
) -> tuple[int, bool]:
    cost = _metadata_header_size(name, value)
    if cost > budget:
        return budget, False
    headers[name] = value
    return budget - cost, True


def gateway_user_metadata_headers(
    *,
    file_id: uuid.UUID,
    blob_id: uuid.UUID,
    folder_id: uuid.UUID,
    meta: dict[str, Any] | None,
) -> dict[str, str]:
    """Build Pithosys ``x-amz-meta-pithosys-*`` headers for gateway HEAD/GET responses."""
    headers: dict[str, str] = {}
    budget = S3_USER_METADATA_MAX_BYTES

    for name, value in (
        (S3_PITHOSYS_FILE_ID_HEADER, str(file_id)),
        (S3_PITHOSYS_BLOB_ID_HEADER, str(blob_id)),
        (S3_PITHOSYS_FOLDER_ID_HEADER, str(folder_id)),
    ):
        budget, added = _try_add_metadata_header(
            headers, budget=budget, name=name, value=value
        )
        if not added:
            log.warning("s3_metadata_lineage_header_dropped", header=name)

    payload = dict(meta or {})
    meta_json = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    budget, added = _try_add_metadata_header(
        headers,
        budget=budget,
        name=S3_PITHOSYS_META_HEADER,
        value=meta_json,
    )
    if not added:
        log.warning(
            "s3_metadata_json_header_dropped",
            bytes=len(meta_json.encode("utf-8")),
            budget=budget,
        )

    return headers
