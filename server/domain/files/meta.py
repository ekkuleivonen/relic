"""Opaque per-file metadata owned by external consumers.

Relic does not impose a schema on ``File.meta``. Upload paths pass through
caller-supplied JSON; consumers patch fields via the files API as needed.
"""

from __future__ import annotations

from typing import Any


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
