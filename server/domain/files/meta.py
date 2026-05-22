"""Opaque per-file metadata owned by external consumers.

Relic does not impose a schema on ``File.meta``. Upload paths pass through
caller-supplied JSON; consumers patch fields via the files API as needed.
"""

from __future__ import annotations

from typing import Any

S3_USER_METADATA_RESERVED_KEYS = frozenset({"relic-user"})


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


def user_metadata_as_s3_headers(meta: dict[str, Any] | None) -> dict[str, str]:
    """Map round-trippable ``File.meta`` entries to ``x-amz-meta-*`` headers."""
    headers: dict[str, str] = {}
    for raw_name, value in (meta or {}).items():
        name = raw_name.strip().lower()
        if not name or name in S3_USER_METADATA_RESERVED_KEYS:
            continue
        if isinstance(value, (dict, list)) or value is None:
            continue
        if not isinstance(value, (str, int, float, bool)):
            continue
        header_value = value if isinstance(value, str) else str(value)
        if "\n" in header_value or "\r" in header_value:
            continue
        headers[f"x-amz-meta-{name}"] = header_value
    return headers
