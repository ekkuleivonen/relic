"""Canonical shape for ``File.meta``."""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

META_SCHEMA_VERSION = "1.0.0"
KvsValue = str | int | float | bool | None


class FileMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    size: int
    extension: str
    mimetype: str
    original_filename: str
    tags: list[str]
    keywords: list[str]
    summary: str | None
    kvs: dict[str, KvsValue]

    @model_validator(mode="after")
    def _schema_version_is_current(self) -> FileMeta:
        if self.schema_version != META_SCHEMA_VERSION:
            raise ValueError(f"Unsupported file meta schema version {self.schema_version!r}")
        return self


def build_file_meta(
    *,
    file_name: str,
    size: int,
    user_meta: dict[str, Any],
    mimetype: str | None = None,
) -> dict[str, Any]:
    """Build the canonical meta shape from upload-time data."""
    extension = PurePosixPath(file_name).suffix.removeprefix(".").lower()
    guessed_mimetype, _ = mimetypes.guess_type(file_name)
    meta = {
        "schema_version": META_SCHEMA_VERSION,
        "size": size,
        "extension": extension,
        "mimetype": mimetype or guessed_mimetype or "application/octet-stream",
        "original_filename": _string_value(user_meta.get("original_filename")) or file_name,
        "tags": _normalize_list(user_meta.get("tags")),
        "keywords": _normalize_list(user_meta.get("keywords")),
        "summary": _string_value(user_meta.get("summary")),
        "kvs": _normalize_kvs(user_meta.get("kvs")),
    }

    for key, value in user_meta.items():
        if key in {
            "schema_version",
            "size",
            "extension",
            "mimetype",
            "original_filename",
            "tags",
            "keywords",
            "summary",
            "kvs",
        }:
            continue
        meta["kvs"][key] = _normalize_kv_value(value)

    return validate_file_meta_dict(meta).model_dump(mode="json")


def merge_parser_meta(*, existing: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    """Merge parser output into file meta, preserving upload-time values on overlap."""
    current = validate_file_meta_dict(existing).model_dump(mode="json")
    parser_meta = validate_file_meta_dict(parsed).model_dump(mode="json")

    return validate_file_meta_dict(
        {
            "schema_version": current["schema_version"],
            "size": current["size"],
            "extension": current["extension"],
            "mimetype": _merge_mimetype(current["mimetype"], parser_meta["mimetype"]),
            "original_filename": current["original_filename"],
            "tags": _merge_lists(current["tags"], parser_meta["tags"]),
            "keywords": _merge_lists(current["keywords"], parser_meta["keywords"]),
            "summary": current["summary"] or parser_meta["summary"],
            "kvs": {**parser_meta["kvs"], **current["kvs"]},
        }
    ).model_dump(mode="json")


def _merge_mimetype(current: str, parsed: str) -> str:
    if current == "application/octet-stream" and parsed != "application/octet-stream":
        return parsed
    return current


def build_parser_meta(
    *,
    existing: dict[str, Any],
    tags: list[str],
    keywords: list[str],
    summary: str | None = None,
    kvs: dict[str, KvsValue],
    mimetype: str | None = None,
) -> dict[str, Any]:
    """Build canonical parser output before merging it into existing meta."""
    current = validate_file_meta_dict(existing).model_dump(mode="json")
    return validate_file_meta_dict(
        {
            "schema_version": current["schema_version"],
            "size": current["size"],
            "extension": current["extension"],
            "mimetype": mimetype or current["mimetype"],
            "original_filename": current["original_filename"],
            "tags": _merge_lists([], tags),
            "keywords": _merge_lists([], keywords),
            "summary": summary,
            "kvs": kvs,
        }
    ).model_dump(mode="json")


def validate_file_meta_dict(meta: dict[str, Any]) -> FileMeta:
    return FileMeta.model_validate(meta)


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError("tags and keywords must be lists or comma-separated strings")
    return _merge_lists([], [_string_value(item) for item in values])


def _merge_lists(left: list[str], right: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in [*left, *right]:
        normalized = _string_value(value)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _normalize_kvs(value: Any) -> dict[str, KvsValue]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("kvs must be an object")
    return {str(key): _normalize_kv_value(v) for key, v in value.items()}


def _normalize_kv_value(value: Any) -> KvsValue:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise ValueError(f"Meta kv values must be scalar, got {type(value).__name__}")


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
