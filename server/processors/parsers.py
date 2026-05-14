"""Shared parser-side helpers for type-specific metadata extractors.

Each parser returns a ``SectionPayload`` — a plain dict with the four
discovery fields the section schema cares about. The processor wraps the
return value into a ``FileMetaSection`` and writes it via ``apply_section``.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from domain.files.meta import KvsValue


class SectionPayload(TypedDict, total=False):
    tags: list[str]
    keywords: list[str]
    summary: str | None
    kvs: dict[str, KvsValue]


def empty_payload(
    *, tags: list[str] | None = None, summary: str | None = None
) -> SectionPayload:
    return {
        "tags": list(tags or []),
        "keywords": [],
        "summary": summary,
        "kvs": {},
    }


def dedupe(values: list[str | None] | tuple[str | None, ...], *, limit: int = 100) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_keyword(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def normalize_keyword(value: Any) -> str | None:
    if value is None:
        return None
    keyword = re.sub(r"\s+", " ", str(value).strip().lower())
    return keyword or None


def normalize_token(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower()
    return token or None


def file_info_filename(file_info: dict[str, Any] | None) -> str:
    """Return the original filename recorded by ``file_info``, or empty."""
    if not file_info:
        return ""
    return str(file_info.get("original_filename") or "")
