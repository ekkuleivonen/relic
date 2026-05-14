"""Canonical shape for ``File.meta``.

The shape is *sectioned*: each processor owns a slot under ``sections.<kind>``
and writes its own ``tags``, ``keywords``, ``summary``, and ``kvs``. The
top-level fields (``size``, ``extension``, ``mimetype``, ``tags``,
``keywords``, ``summary``, ``kvs``) are a derived merged view of the user
upload data plus every completed section, recomputed every time a section is
written. Read-only callers (search, UI) can keep using the flat top level;
writers must go through ``apply_section`` so the merge stays consistent.
"""

from __future__ import annotations

import datetime as dt
import mimetypes
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from constants import META_SCHEMA_VERSION

KvsValue = str | int | float | bool | None
SectionStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]


class FileMetaSection(BaseModel):
    """One processor's slice of file metadata."""

    model_config = ConfigDict(extra="forbid")

    status: SectionStatus = "pending"
    extracted_at: dt.datetime | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    summary: str | None = None
    kvs: dict[str, KvsValue] = Field(default_factory=dict)
    error_class: str | None = None
    error_message: str | None = None


class FileMeta(BaseModel):
    """Persisted file metadata.

    Top-level fields (``size``/``extension``/``mimetype``/``tags``/...) are
    *derived* from upload data plus completed processor sections. They exist
    so search and the filesystem UI can read flat shapes without traversing
    sections, but they should only ever be written through ``apply_section``
    or ``init_file_meta``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    size: int
    extension: str
    mimetype: str
    original_filename: str

    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    summary: str | None = None
    kvs: dict[str, KvsValue] = Field(default_factory=dict)

    user_tags: list[str] = Field(default_factory=list)
    user_keywords: list[str] = Field(default_factory=list)
    user_summary: str | None = None
    user_kvs: dict[str, KvsValue] = Field(default_factory=dict)

    sections: dict[str, FileMetaSection] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _schema_version_is_current(self) -> FileMeta:
        if self.schema_version != META_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported file meta schema version {self.schema_version!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def init_file_meta(
    *,
    file_name: str,
    size: int,
    user_meta: dict[str, Any],
    mimetype: str | None = None,
) -> dict[str, Any]:
    """Build the canonical meta shape from upload-time data.

    Sections start empty; processors will populate them. Top-level fields
    contain just the user upload data until the first section completes.
    """
    extension = PurePosixPath(file_name).suffix.removeprefix(".").lower()
    guessed_mimetype, _ = mimetypes.guess_type(file_name)
    effective_mimetype = mimetype or guessed_mimetype or "application/octet-stream"

    user_tags = _normalize_list(user_meta.get("tags"))
    user_keywords = _normalize_list(user_meta.get("keywords"))
    user_summary = _string_value(user_meta.get("summary"))
    user_kvs = _normalize_kvs(user_meta.get("kvs"))

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
        user_kvs[str(key)] = _normalize_kv_value(value)

    meta = {
        "schema_version": META_SCHEMA_VERSION,
        "size": size,
        "extension": extension,
        "mimetype": effective_mimetype,
        "original_filename": _string_value(user_meta.get("original_filename"))
        or file_name,
        "user_tags": user_tags,
        "user_keywords": user_keywords,
        "user_summary": user_summary,
        "user_kvs": user_kvs,
        "sections": {},
        # placeholders rebuilt by _refresh_top_level
        "tags": [],
        "keywords": [],
        "summary": None,
        "kvs": {},
    }
    return _refresh_top_level(meta)


def apply_section(
    meta: dict[str, Any],
    *,
    kind: str,
    section: FileMetaSection | dict[str, Any],
    base_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one processor's section and recompute the merged top level.

    ``base_overrides`` may set top-level ``size``/``extension``/``mimetype``
    when the writing processor (typically ``file_info``) wants to update
    upload-time defaults from observed bytes.
    """
    parsed = validate_file_meta_dict(meta).model_dump(mode="json")
    parsed_section = (
        section
        if isinstance(section, FileMetaSection)
        else FileMetaSection.model_validate(section)
    )
    parsed["sections"][kind] = parsed_section.model_dump(mode="json")
    if base_overrides:
        for field_name, value in base_overrides.items():
            if field_name not in {"size", "extension", "mimetype"}:
                raise ValueError(
                    f"base_overrides may only set size/extension/mimetype, "
                    f"got {field_name!r}"
                )
            parsed[field_name] = value
    return _refresh_top_level(parsed)


def mark_section(
    meta: dict[str, Any],
    *,
    kind: str,
    status: SectionStatus,
    error_class: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Update only the section's status/error fields without changing data."""
    parsed = validate_file_meta_dict(meta).model_dump(mode="json")
    existing = parsed["sections"].get(kind, FileMetaSection().model_dump(mode="json"))
    existing["status"] = status
    if status == "in_progress":
        existing["error_class"] = None
        existing["error_message"] = None
    else:
        existing["error_class"] = error_class
        existing["error_message"] = error_message
    parsed["sections"][kind] = existing
    return _refresh_top_level(parsed)


def validate_file_meta_dict(meta: dict[str, Any]) -> FileMeta:
    return FileMeta.model_validate(meta)


# ---------------------------------------------------------------------------
# Internal merge logic
# ---------------------------------------------------------------------------


def _refresh_top_level(meta: dict[str, Any]) -> dict[str, Any]:
    sections: dict[str, dict[str, Any]] = meta.get("sections") or {}

    tags = list(meta.get("user_tags") or [])
    keywords = list(meta.get("user_keywords") or [])
    summary_candidates: list[str] = []
    if meta.get("user_summary"):
        summary_candidates.append(meta["user_summary"])

    merged_kvs: dict[str, KvsValue] = {}
    for key, value in (meta.get("user_kvs") or {}).items():
        merged_kvs[str(key)] = _normalize_kv_value(value)

    for kind in sorted(sections):
        section = sections[kind]
        if section.get("status") != "completed":
            continue
        for tag in section.get("tags") or []:
            if tag and tag not in tags:
                tags.append(tag)
        for keyword in section.get("keywords") or []:
            if keyword and keyword not in keywords:
                keywords.append(keyword)
        if section.get("summary"):
            summary_candidates.append(section["summary"])
        for key, value in (section.get("kvs") or {}).items():
            merged_kvs[f"{kind}.{key}"] = _normalize_kv_value(value)

    file_info = sections.get("file_info") or {}
    file_info_kvs = file_info.get("kvs") if file_info.get("status") == "completed" else None
    if isinstance(file_info_kvs, dict):
        observed_size = file_info_kvs.get("size")
        if isinstance(observed_size, int):
            meta["size"] = observed_size
        observed_mimetype = file_info_kvs.get("mimetype")
        if isinstance(observed_mimetype, str) and observed_mimetype:
            meta["mimetype"] = observed_mimetype
        observed_extension = file_info_kvs.get("extension")
        if isinstance(observed_extension, str):
            meta["extension"] = observed_extension

    meta["tags"] = tags
    meta["keywords"] = keywords
    meta["summary"] = _pick_summary(summary_candidates, file_info=file_info)
    meta["kvs"] = merged_kvs

    return validate_file_meta_dict(meta).model_dump(mode="json")


def _pick_summary(
    candidates: list[str], *, file_info: dict[str, Any] | None
) -> str | None:
    """Prefer file_info's summary, then user-provided, then any other section.

    Sections beyond ``file_info`` are appended in alphabetical order which gives
    them a stable but otherwise arbitrary tiebreaker. The first non-empty wins.
    """
    file_info_summary = (
        file_info.get("summary") if file_info and file_info.get("status") == "completed" else None
    )
    ordered = [file_info_summary, *candidates]
    for value in ordered:
        if value:
            return value
    return None


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError("tags and keywords must be lists or comma-separated strings")
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        normalized = _string_value(raw)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


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


# ---------------------------------------------------------------------------
# Parser-side helpers (used by toolchains in processors/kinds/*_meta)
# ---------------------------------------------------------------------------


def build_section_payload(
    *,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    summary: str | None = None,
    kvs: dict[str, KvsValue] | None = None,
    status: SectionStatus = "completed",
    extracted_at: dt.datetime | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
) -> FileMetaSection:
    """Convenience builder that normalizes lists/kvs the same way meta does."""
    return FileMetaSection(
        status=status,
        extracted_at=extracted_at,
        tags=_normalize_list(tags),
        keywords=_normalize_list(keywords),
        summary=_string_value(summary),
        kvs=_normalize_kvs(kvs),
        error_class=error_class,
        error_message=error_message,
    )


# ---------------------------------------------------------------------------
# Discovery-shape helpers for type-meta parser modules.
#
# Each parser builds a small dict matching the ``ParserDiscovery`` shape via
# ``build_parser_discovery``. The corresponding processor extracts that into
# a section payload via ``parser_discovery_to_section_kwargs``.
# ---------------------------------------------------------------------------


def build_parser_discovery(
    *,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    summary: str | None = None,
    kvs: dict[str, KvsValue] | None = None,
) -> dict[str, Any]:
    """Build a parser's discovery output. Returns a normalized, plain dict."""
    return {
        "tags": _normalize_list(tags),
        "keywords": _normalize_list(keywords),
        "summary": _string_value(summary),
        "kvs": _normalize_kvs(kvs),
    }


def empty_parser_discovery(
    *,
    tags: list[str] | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    return build_parser_discovery(tags=tags, summary=summary)
