"""Video parser. Writes compact discovery metadata into file meta.

This parser intentionally handles lightweight container structure directly for
metadata. It currently supports MP4/MOV atoms and RIFF/AVI chunks.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from file_meta import build_file_meta, build_parser_meta
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_CONTAINER_BOXES = {b"moov", b"trak", b"mdia"}
_VIDEO_EXTENSIONS = {"avi", "mkv", "mov", "mp4", "webm"}


def empty_video_meta(*, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shape matching parse() output for failed or unavailable video parsing."""
    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=["video"],
        keywords=[],
        kvs={},
    )


def parse_video(*, content: bytes, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse video bytes for storage in file meta. Never raises."""
    if not content:
        return empty_video_meta(existing_meta=existing_meta)
    try:
        return parse(content, existing_meta=existing_meta)
    except Exception as exc:
        log.warning("video_parse_failed", error=str(exc))
        return empty_video_meta(existing_meta=existing_meta)


def parse(content: bytes, *, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse supported video bytes into the common discovery meta dict."""
    details = _parse_mp4(content, existing_meta=existing_meta)
    if not details["container"]:
        details = _parse_avi(content, existing_meta=existing_meta)
    if not details["container"]:
        raise ValueError("Unsupported video container")
    return _build_discovery_meta(details=details, existing_meta=existing_meta)


def _parse_mp4(content: bytes, *, existing_meta: dict[str, Any] | None) -> dict[str, Any]:
    details: dict[str, Any] = {
        "container": None,
        "duration_seconds": None,
        "width": None,
        "height": None,
        "has_audio": False,
        "has_video": False,
        "codec": None,
        "filename_keywords": _filename_keywords(_original_filename(existing_meta)),
    }

    if not _has_mp4_signature(content):
        return details

    details["container"] = _container_from_meta(existing_meta)
    atoms = list(_iter_atoms(content, 0, len(content)))
    for atom in atoms:
        if atom.kind == b"ftyp":
            details["container"] = _container_from_ftyp(
                content[atom.payload_start : atom.payload_end],
                fallback=details["container"],
            )
        _read_mp4_atom(content=content, atom=atom, details=details)
    return details


def _parse_avi(content: bytes, *, existing_meta: dict[str, Any] | None) -> dict[str, Any]:
    details: dict[str, Any] = {
        "container": None,
        "duration_seconds": None,
        "width": None,
        "height": None,
        "has_audio": False,
        "has_video": False,
        "codec": None,
        "filename_keywords": _filename_keywords(_original_filename(existing_meta)),
    }

    if not _has_avi_signature(content):
        return details

    details["container"] = "avi"
    _read_avi_chunks(content=content, start=12, end=len(content), details=details)
    return details


def _read_avi_chunks(*, content: bytes, start: int, end: int, details: dict[str, Any]) -> None:
    for chunk in _iter_riff_chunks(content, start, end):
        payload = content[chunk.payload_start : chunk.payload_end]
        if chunk.kind == b"avih":
            _parse_avih(payload=payload, details=details)
        elif chunk.kind == b"strh":
            _parse_strh(payload=payload, details=details)
        elif chunk.kind == b"LIST":
            _read_avi_chunks(
                content=content,
                start=chunk.payload_start + 4,
                end=chunk.payload_end,
                details=details,
            )


def _parse_avih(*, payload: bytes, details: dict[str, Any]) -> None:
    if len(payload) < 40:
        return
    microseconds_per_frame = struct.unpack("<I", payload[0:4])[0]
    total_frames = struct.unpack("<I", payload[16:20])[0]
    width = struct.unpack("<I", payload[32:36])[0]
    height = struct.unpack("<I", payload[36:40])[0]
    if microseconds_per_frame and total_frames:
        details["duration_seconds"] = (microseconds_per_frame * total_frames) / 1_000_000
    details["width"] = width or details["width"]
    details["height"] = height or details["height"]


def _parse_strh(*, payload: bytes, details: dict[str, Any]) -> None:
    if len(payload) < 8:
        return
    stream_type = payload[0:4]
    handler = payload[4:8]
    if stream_type == b"vids":
        details["has_video"] = True
        codec = handler.decode("ascii", errors="ignore").strip().lower()
        details["codec"] = codec or details["codec"]
    elif stream_type == b"auds":
        details["has_audio"] = True


def _read_mp4_atom(*, content: bytes, atom: "_Atom", details: dict[str, Any]) -> None:
    payload = content[atom.payload_start : atom.payload_end]
    if atom.kind == b"mvhd":
        details["duration_seconds"] = _parse_mvhd(payload)
    elif atom.kind == b"trak":
        track_details = _parse_track(payload)
        if track_details["handler"] == "vide":
            details["has_video"] = True
            if track_details["width"]:
                details["width"] = track_details["width"]
            if track_details["height"]:
                details["height"] = track_details["height"]
        elif track_details["handler"] == "soun":
            details["has_audio"] = True
    elif atom.kind in _CONTAINER_BOXES:
        for child in _iter_atoms(content, atom.payload_start, atom.payload_end):
            _read_mp4_atom(content=content, atom=child, details=details)


def _parse_track(payload: bytes) -> dict[str, Any]:
    details: dict[str, Any] = {"handler": None, "width": None, "height": None}
    for atom in _iter_atoms(payload, 0, len(payload)):
        child = payload[atom.payload_start : atom.payload_end]
        if atom.kind == b"tkhd":
            width, height = _parse_tkhd(child)
            details["width"] = width
            details["height"] = height
        elif atom.kind == b"mdia":
            details["handler"] = _track_handler(child)
    return details


def _track_handler(mdia_payload: bytes) -> str | None:
    for atom in _iter_atoms(mdia_payload, 0, len(mdia_payload)):
        if atom.kind != b"hdlr":
            continue
        payload = mdia_payload[atom.payload_start : atom.payload_end]
        if len(payload) >= 12:
            return payload[8:12].decode("ascii", errors="ignore")
    return None


def _parse_mvhd(payload: bytes) -> float | None:
    if len(payload) < 24:
        return None
    version = payload[0]
    if version == 1:
        if len(payload) < 36:
            return None
        timescale = struct.unpack(">I", payload[20:24])[0]
        duration = struct.unpack(">Q", payload[24:32])[0]
    else:
        timescale = struct.unpack(">I", payload[12:16])[0]
        duration = struct.unpack(">I", payload[16:20])[0]
    if timescale <= 0:
        return None
    return duration / timescale


def _parse_tkhd(payload: bytes) -> tuple[int | None, int | None]:
    if len(payload) < 84:
        return None, None
    version = payload[0]
    width_offset = 88 if version == 1 else 76
    if len(payload) < width_offset + 8:
        return None, None
    width_fixed, height_fixed = struct.unpack(">II", payload[width_offset : width_offset + 8])
    width = width_fixed >> 16
    height = height_fixed >> 16
    return (width or None), (height or None)


def _build_discovery_meta(
    *, details: dict[str, Any], existing_meta: dict[str, Any] | None
) -> dict[str, Any]:
    container = details["container"]
    width = details["width"]
    height = details["height"]
    duration = details["duration_seconds"]
    role_tags = _role_tags(details["filename_keywords"], container=container)

    tags: list[str | None] = ["video", container, *role_tags]
    tags.append("has-audio" if details["has_audio"] else "silent")
    length_tag = _length_tag(duration)
    if length_tag:
        tags.append(length_tag)
    quality_tag = _quality_tag(width=width, height=height)
    if quality_tag:
        tags.append(quality_tag)
    if width and height and height > width:
        tags.append("vertical")

    keywords = _dedupe(
        [
            *details["filename_keywords"],
            container,
            details.get("codec"),
        ],
        limit=_MAX_KEYWORDS,
    )

    kvs: dict[str, Any] = {}
    if duration is not None:
        kvs["duration_seconds"] = round(duration, 3)
    if width is not None:
        kvs["width"] = width
    if height is not None:
        kvs["height"] = height

    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=_dedupe(tags, limit=12),
        keywords=keywords,
        summary=_summary(
            container=container,
            width=width,
            height=height,
            has_audio=details["has_audio"],
            length_tag=length_tag,
            role_tags=role_tags,
        ),
        kvs=kvs,
    )


def _has_mp4_signature(content: bytes) -> bool:
    if len(content) < 12:
        return False
    return content[4:8] == b"ftyp"


def _has_avi_signature(content: bytes) -> bool:
    return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"AVI "


def _container_from_ftyp(payload: bytes, *, fallback: str | None) -> str | None:
    if len(payload) < 4:
        return fallback
    brand = payload[:4]
    if brand == b"qt  ":
        return "mov"
    if brand in {b"isom", b"mp41", b"mp42", b"avc1", b"iso2"}:
        return "mp4"
    return fallback or brand.decode("ascii", errors="ignore").strip().lower() or None


def _container_from_meta(existing_meta: dict[str, Any] | None) -> str | None:
    extension = _extension(existing_meta)
    if extension in _VIDEO_EXTENSIONS:
        return extension
    return None


def _role_tags(filename_keywords: list[str], *, container: str | None) -> list[str]:
    words = set(filename_keywords)
    roles: list[str] = []
    if {"screen", "recording"}.issubset(words) or "screencast" in words:
        roles.append("screen-recording")
    if any(word.startswith("img") for word in words) and container in {"mov", "mp4"}:
        roles.append("phone-video")
    if words & {"movie", "film"}:
        roles.append("movie")
    if words & {"clip", "clips"}:
        roles.append("clip")
    return roles


def _length_tag(duration: float | None) -> str | None:
    if duration is None:
        return None
    if duration < 5 * 60:
        return "short"
    if duration >= 45 * 60:
        return "long"
    return None


def _quality_tag(*, width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    largest = max(width, height)
    smallest = min(width, height)
    if largest >= 3840 or smallest >= 2160:
        return "4k"
    if largest >= 1280 or smallest >= 720:
        return "hd"
    return None


def _summary(
    *,
    container: str | None,
    width: int | None,
    height: int | None,
    has_audio: bool,
    length_tag: str | None,
    role_tags: list[str],
) -> str:
    dimensions = _dimension_summary(width=width, height=height)
    parts = [
        length_tag,
        "vertical" if width and height and height > width else None,
        dimensions,
        container,
        role_tags[0] if role_tags else "video",
        "with audio" if has_audio else "without audio",
    ]
    return " ".join(part for part in parts if part)


def _dimension_summary(*, width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    landscape_height = min(width, height)
    if landscape_height >= 2160:
        return "4k"
    if landscape_height >= 1080:
        return "1080p"
    if landscape_height >= 720:
        return "720p"
    return None


def _filename_keywords(filename: str) -> list[str]:
    stem = PurePosixPath(filename).stem if filename else ""
    return [
        word
        for word in re.split(r"[^A-Za-z0-9]+", stem.lower())
        if len(word) >= 2 and not word.isdigit()
    ]


def _original_filename(existing_meta: dict[str, Any] | None) -> str:
    if not existing_meta:
        return ""
    return str(existing_meta.get("original_filename") or "")


def _extension(existing_meta: dict[str, Any] | None) -> str:
    if not existing_meta:
        return ""
    return str(existing_meta.get("extension") or "").lower()


def _dedupe(values: Iterable[str | None], *, limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize_keyword(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _normalize_keyword(value: Any) -> str | None:
    if value is None:
        return None
    keyword = re.sub(r"\s+", " ", str(value).strip().lower())
    return keyword or None


class _Atom:
    def __init__(self, *, kind: bytes, payload_start: int, payload_end: int) -> None:
        self.kind = kind
        self.payload_start = payload_start
        self.payload_end = payload_end


class _RiffChunk:
    def __init__(self, *, kind: bytes, payload_start: int, payload_end: int) -> None:
        self.kind = kind
        self.payload_start = payload_start
        self.payload_end = payload_end


def _iter_atoms(content: bytes, start: int, end: int) -> Iterable[_Atom]:
    offset = start
    while offset + 8 <= end:
        size, kind = struct.unpack(">I4s", content[offset : offset + 8])
        header_size = 8
        if size == 1:
            if offset + 16 > end:
                break
            size = struct.unpack(">Q", content[offset + 8 : offset + 16])[0]
            header_size = 16
        elif size == 0:
            size = end - offset
        if size < header_size or offset + size > end:
            break
        yield _Atom(
            kind=kind,
            payload_start=offset + header_size,
            payload_end=offset + size,
        )
        offset += size


def _iter_riff_chunks(content: bytes, start: int, end: int) -> Iterable[_RiffChunk]:
    offset = start
    while offset + 8 <= end:
        kind = content[offset : offset + 4]
        size = struct.unpack("<I", content[offset + 4 : offset + 8])[0]
        payload_start = offset + 8
        payload_end = payload_start + size
        if payload_end > end:
            break
        yield _RiffChunk(kind=kind, payload_start=payload_start, payload_end=payload_end)
        offset = payload_end + (size % 2)
