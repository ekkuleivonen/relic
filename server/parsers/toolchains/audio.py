"""Audio parser. Writes compact discovery metadata into file meta."""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from mutagen import File as MutagenFile
from mutagen import MutagenError

from file_meta import build_file_meta, build_parser_meta
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_LOSSLESS_CONTAINERS = {"aiff", "ape", "flac", "wave", "wav"}
_COMPRESSED_CONTAINERS = {"aac", "mp3", "mp4", "m4a", "ogg", "opus"}
_TAG_ALIASES = {
    "title": ("title", "TIT2", "\xa9nam"),
    "artist": ("artist", "TPE1", "\xa9ART"),
    "album": ("album", "TALB", "\xa9alb"),
    "album_artist": ("albumartist", "album_artist", "TPE2", "aART"),
    "genre": ("genre", "TCON", "\xa9gen"),
    "year": ("date", "year", "TDRC", "TYER", "\xa9day"),
    "track": ("tracknumber", "track", "TRCK", "trkn"),
    "disc": ("discnumber", "disc", "TPOS", "disk"),
}


def empty_audio_meta(*, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shape matching parse() output for failed or unavailable audio parsing."""
    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=["audio"],
        keywords=[],
        kvs={},
    )


def parse_audio(*, content: bytes, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse audio bytes for storage in file meta. Never raises."""
    if not content:
        return empty_audio_meta(existing_meta=existing_meta)
    try:
        return parse(content, existing_meta=existing_meta)
    except (MutagenError, OSError, ValueError) as exc:
        log.warning("audio_parse_failed", error=str(exc))
        return empty_audio_meta(existing_meta=existing_meta)
    except Exception as exc:
        log.warning("audio_parse_failed", error=str(exc))
        return empty_audio_meta(existing_meta=existing_meta)


def parse(content: bytes, *, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse audio bytes into the common discovery meta dict."""
    audio = MutagenFile(io.BytesIO(content))
    if audio is None:
        raise ValueError("Unsupported audio file")

    details = _extract_details(audio=audio, existing_meta=existing_meta)
    return _build_discovery_meta(details=details, existing_meta=existing_meta)


def _extract_details(*, audio: Any, existing_meta: dict[str, Any] | None) -> dict[str, Any]:
    info = getattr(audio, "info", None)
    tags = getattr(audio, "tags", None)
    container = _container(audio=audio, existing_meta=existing_meta)
    tag_values = _common_tag_values(tags)
    filename = _original_filename(existing_meta)

    return {
        "container": container,
        "codec": _codec(info=info, container=container),
        "duration_seconds": _duration(info),
        "channels": _channels(info),
        "tag_values": tag_values,
        "filename_keywords": _filename_keywords(filename),
    }


def _build_discovery_meta(
    *, details: dict[str, Any], existing_meta: dict[str, Any] | None
) -> dict[str, Any]:
    container = details["container"]
    codec = details["codec"]
    duration = details["duration_seconds"]
    channels = details["channels"]
    tag_values = details["tag_values"]
    filename_keywords = details["filename_keywords"]
    role_tags = _role_tags(tag_values=tag_values, filename_keywords=filename_keywords)

    tags: list[str | None] = ["audio", container, *role_tags]
    if container in _LOSSLESS_CONTAINERS:
        tags.append("lossless")
    elif container in _COMPRESSED_CONTAINERS:
        tags.append("compressed")
    if channels == 1:
        tags.append("mono")
    elif channels and channels >= 2:
        tags.append("stereo")

    length_tag = _length_tag(duration)
    if length_tag:
        tags.append(length_tag)

    keywords = _dedupe(
        [
            tag_values.get("title"),
            tag_values.get("artist"),
            tag_values.get("album"),
            tag_values.get("album_artist"),
            tag_values.get("genre"),
            tag_values.get("year"),
            tag_values.get("track"),
            tag_values.get("disc"),
            *filename_keywords,
            container,
            codec,
        ],
        limit=_MAX_KEYWORDS,
    )

    kvs: dict[str, Any] = {}
    if duration is not None:
        kvs["duration_seconds"] = round(duration, 3)

    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=_dedupe(tags, limit=12),
        keywords=keywords,
        summary=_summary(
            container=container,
            channels=channels,
            length_tag=length_tag,
            role_tags=role_tags,
            tag_values=tag_values,
        ),
        kvs=kvs,
    )


def _common_tag_values(tags: Any) -> dict[str, str | None]:
    return {
        field: _first_tag_value(tags, aliases)
        for field, aliases in _TAG_ALIASES.items()
    }


def _first_tag_value(tags: Any, aliases: Iterable[str]) -> str | None:
    if not tags:
        return None
    for alias in aliases:
        try:
            value = tags.get(alias)
        except AttributeError:
            value = None
        normalized = _normalize_tag_value(value)
        if normalized:
            return normalized
    return None


def _normalize_tag_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list | tuple):
        if not value:
            return None
        value = value[0]
    if hasattr(value, "text"):
        text = getattr(value, "text")
        if isinstance(text, list | tuple):
            value = text[0] if text else None
        else:
            value = text
    if isinstance(value, list | tuple):
        if not value:
            return None
        value = value[0]
    if isinstance(value, tuple) and value and isinstance(value[0], int):
        value = "/".join(str(part) for part in value if part)
    return _normalize_keyword(value)


def _container(*, audio: Any, existing_meta: dict[str, Any] | None) -> str | None:
    extension = _extension(existing_meta)
    if extension in {"aac", "aiff", "ape", "flac", "m4a", "mp3", "ogg", "opus", "wav"}:
        return extension
    type_name = type(audio).__name__.lower()
    if type_name == "wave":
        return "wav"
    if type_name == "mp4":
        return "m4a"
    return type_name or extension or None


def _codec(*, info: Any, container: str | None) -> str | None:
    if container == "wav" and getattr(info, "audio_format", None) == 1:
        return "pcm"
    if container == "flac":
        return "flac"
    if container == "mp3":
        return "mp3"
    if container in {"ogg", "opus"}:
        return container
    codec = getattr(info, "codec", None)
    return _normalize_keyword(codec)


def _duration(info: Any) -> float | None:
    value = getattr(info, "length", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _channels(info: Any) -> int | None:
    value = getattr(info, "channels", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _role_tags(
    *, tag_values: dict[str, str | None], filename_keywords: list[str]
) -> list[str]:
    observed = " ".join(
        value
        for value in [
            tag_values.get("title"),
            tag_values.get("album"),
            tag_values.get("genre"),
            *filename_keywords,
        ]
        if value
    )
    words = set(re.split(r"[^a-z0-9]+", observed.lower()))

    roles: list[str] = []
    if words & {"podcast", "podcasts", "episode"}:
        roles.append("podcast")
    if words & {"audiobook", "audiobooks"} or "audio book" in observed.lower():
        roles.append("audiobook")
    if words & {"voice", "spoken", "speech"} or "spoken word" in observed.lower():
        roles.append("voice")
    if not roles and (
        tag_values.get("artist")
        or tag_values.get("album_artist")
        or tag_values.get("genre")
        or words & {"music", "song", "track", "album"}
    ):
        roles.append("music")
    return roles


def _length_tag(duration: float | None) -> str | None:
    if duration is None:
        return None
    if duration < 5 * 60:
        return "short"
    if duration >= 45 * 60:
        return "long"
    return None


def _summary(
    *,
    container: str | None,
    channels: int | None,
    length_tag: str | None,
    role_tags: list[str],
    tag_values: dict[str, str | None],
) -> str:
    parts = [
        length_tag,
        "mono" if channels == 1 else "stereo" if channels and channels >= 2 else None,
        container,
        role_tags[0] if role_tags else None,
        None if role_tags else "audio",
    ]
    summary = " ".join(part for part in parts if part)
    artist = tag_values.get("artist")
    if artist and "music" in role_tags:
        summary = f"{summary} by {artist}"
    return summary or "audio file"


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
