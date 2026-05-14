"""Plain text parser. Writes compact discovery metadata into file meta."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import IO, Any

from charset_normalizer import from_bytes

from domain.files.meta import build_parser_discovery, empty_parser_discovery
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_MAX_HEADING_KEYWORDS = 15
_MAX_KEY_VALUE_KEYWORDS = 20
_MAX_REPEATED_KEYWORDS = 20
_MIN_PRINTABLE_RATIO = 0.85
_LONG_TEXT_WORDS = 10_000
_STOPWORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "have",
    "hereby",
    "into",
    "not",
    "that",
    "the",
    "this",
    "to",
    "with",
    "you",
}
_CONFIG_EXTENSIONS = {"cfg", "conf", "config", "env", "ini", "properties", "toml", "yaml", "yml"}
_TEXT_EXTENSIONS = {
    "adoc",
    "cfg",
    "conf",
    "config",
    "css",
    "env",
    "ini",
    "log",
    "md",
    "properties",
    "rst",
    "text",
    "toml",
    "txt",
    "yaml",
    "yml",
}


def empty_text_meta(*, file_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shape matching parse() output for failed or unavailable text parsing."""
    return build_parser_discovery(
        tags=["text", "plain-text"],
        keywords=[],
        kvs={},
    )


def parse_text(*, content: bytes, file_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse text bytes for storage in file meta. Never raises."""
    try:
        return parse(content, file_info=file_info)
    except Exception as exc:
        log.warning("text_parse_failed", error=str(exc))
        return empty_text_meta(file_info=file_info)


def parse(
    content: bytes | IO[bytes], *, file_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse readable text bytes into the common discovery meta dict."""
    full_bytes = content if isinstance(content, bytes) else content.read()
    if full_bytes and _looks_binary(full_bytes):
        return empty_text_meta(file_info=file_info)

    text = _decode_text(full_bytes)
    details = _extract_details(text=text, file_info=file_info)
    return _build_discovery_meta(details=details, file_info=file_info)


def _extract_details(*, text: str, file_info: dict[str, Any] | None) -> dict[str, Any]:
    lines = text.splitlines()
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text)
    filename = _original_filename(file_info)
    extension = _extension(file_info)

    return {
        "line_count": len(lines),
        "word_count": len(words),
        "filename": filename,
        "extension": extension,
        "empty": not text.strip(),
        "is_log": _is_log(filename=filename, extension=extension, lines=lines),
        "is_config": _is_config(filename=filename, extension=extension, text=text),
        "is_readme": _is_readme(filename=filename, lines=lines),
        "is_license": _is_license(filename=filename, text=text),
        "is_notes": _is_notes(filename=filename, lines=lines),
        "keywords": _keywords(
            filename=filename,
            extension=extension,
            text=text,
            lines=lines,
            words=words,
        ),
    }


def _build_discovery_meta(
    *, details: dict[str, Any], file_info: dict[str, Any] | None
) -> dict[str, Any]:
    word_count = details["word_count"]
    tags: list[str | None] = ["text", "plain-text"]
    if details["empty"]:
        tags.append("empty")
    if details["is_log"]:
        tags.append("log")
    if details["is_config"]:
        tags.append("config")
    if details["is_readme"]:
        tags.append("readme")
    if details["is_license"]:
        tags.append("license")
    if details["is_notes"] and not details["empty"]:
        tags.append("notes")

    length_tag = _length_tag(word_count)
    if length_tag and not details["empty"]:
        tags.append(length_tag)

    kvs = {
        "line_count": details["line_count"],
        "word_count": word_count,
    }

    return build_parser_discovery(
        tags=_dedupe(tags, limit=12),
        keywords=_dedupe(details["keywords"], limit=_MAX_KEYWORDS),
        summary=_summary(details=details, length_tag=length_tag),
        kvs=kvs,
    )


def _decode_text(content: bytes) -> str:
    if not content:
        return ""
    for bom, encoding in (
        (b"\xff\xfe\x00\x00", "utf-32-le"),
        (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xff\xfe", "utf-16-le"),
        (b"\xfe\xff", "utf-16-be"),
        (b"\xef\xbb\xbf", "utf-8-sig"),
    ):
        if content.startswith(bom):
            return content.decode(encoding, errors="replace")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        detected = from_bytes(content).best()
        if detected is not None and detected.encoding:
            return content.decode(detected.encoding, errors="replace")
        return content.decode("latin-1", errors="replace")


def _looks_binary(content: bytes) -> bool:
    if b"\x00" in content:
        return True
    if not content:
        return False
    sample = content[:4096]
    printable = sum(byte in b"\n\r\t\f\b" or 32 <= byte <= 126 or byte >= 128 for byte in sample)
    return printable / len(sample) < _MIN_PRINTABLE_RATIO


def _keywords(
    *,
    filename: str,
    extension: str,
    text: str,
    lines: list[str],
    words: list[str],
) -> list[str | None]:
    return [
        *_filename_keywords(filename=filename, extension=extension),
        *_heading_keywords(lines),
        *_key_value_keywords(lines),
        *_log_keywords(lines),
        *_repeated_keywords(words),
        *_license_keywords(text),
    ]


def _filename_keywords(*, filename: str, extension: str) -> list[str]:
    stem = PurePosixPath(filename).stem if filename else ""
    words = [
        word
        for word in re.split(r"[^A-Za-z0-9_+-]+", stem.lower())
        if word and not word.isdigit()
    ]
    if extension in _TEXT_EXTENSIONS:
        words.append(extension)
    return words


def _heading_keywords(lines: list[str]) -> list[str]:
    keywords: list[str] = []
    for line in lines[:30]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "=", "-")):
            keywords.extend(_word_keywords(stripped))
            continue
        if len(stripped) <= 80 and stripped.isupper():
            keywords.extend(_word_keywords(stripped))
    return _dedupe(keywords, limit=_MAX_HEADING_KEYWORDS)


def _key_value_keywords(lines: list[str]) -> list[str]:
    labels: list[str] = []
    for line in lines[:200]:
        match = re.match(r"\s*([A-Za-z][A-Za-z0-9_.-]{1,80})\s*[:=]\s*\S+", line)
        if match:
            labels.append(match.group(1))
    return _dedupe(labels, limit=_MAX_KEY_VALUE_KEYWORDS)


def _log_keywords(lines: list[str]) -> list[str]:
    keywords: list[str] = []
    for line in lines[:50]:
        keywords.extend(re.findall(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|TRACE)\b", line))
    return _dedupe(keywords, limit=10)


def _repeated_keywords(words: list[str]) -> list[str]:
    normalized_words = [
        word.lower()
        for word in words
        if len(word) >= 3 and word.lower() not in _STOPWORDS and not word.isdigit()
    ]
    counts = Counter(normalized_words)
    ranked = sorted(counts, key=lambda word: (-counts[word], normalized_words.index(word)))
    return [word for word in ranked if counts[word] >= 2][:_MAX_REPEATED_KEYWORDS]


def _license_keywords(text: str) -> list[str]:
    lower = text.lower()
    if "mit license" in lower:
        return ["mit", "license"]
    if "apache license" in lower:
        return ["apache", "license"]
    if "gnu general public license" in lower:
        return ["gnu", "gpl", "license"]
    return []


def _word_keywords(text: str) -> list[str]:
    return [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text)
        if len(word) >= 3 and word.lower() not in _STOPWORDS
    ]


def _is_log(*, filename: str, extension: str, lines: list[str]) -> bool:
    if extension == "log" or "log" in _filename_keywords(filename=filename, extension=""):
        return True
    log_lines = 0
    for line in lines[:20]:
        if re.match(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", line):
            log_lines += 1
        elif re.search(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|TRACE)\b", line):
            log_lines += 1
    return bool(lines) and log_lines >= max(2, len(lines[:20]) // 2)


def _is_config(*, filename: str, extension: str, text: str) -> bool:
    name = PurePosixPath(filename).name.lower()
    if extension in _CONFIG_EXTENSIONS or name in {".env", "config", "settings"}:
        return True
    key_value_lines = len(re.findall(r"(?m)^\s*[A-Za-z][A-Za-z0-9_.-]{1,80}\s*[:=]\s*\S+", text))
    return key_value_lines >= 2


def _is_readme(*, filename: str, lines: list[str]) -> bool:
    name = PurePosixPath(filename).name.lower()
    if name.startswith("readme"):
        return True
    return bool(lines) and "readme" in lines[0].lower()


def _is_license(*, filename: str, text: str) -> bool:
    name = PurePosixPath(filename).name.lower()
    if name in {"license", "licence", "copying"} or name.startswith(("license.", "licence.")):
        return True
    lower = text.lower()
    return "mit license" in lower or "apache license" in lower or "gnu general public license" in lower


def _is_notes(*, filename: str, lines: list[str]) -> bool:
    filename_words = _filename_keywords(filename=filename, extension="")
    if "note" in filename_words or "notes" in filename_words:
        return True
    return bool(lines) and "notes" in lines[0].lower()


def _length_tag(word_count: int) -> str | None:
    if word_count == 0:
        return None
    if word_count < 500:
        return "short"
    if word_count >= _LONG_TEXT_WORDS:
        return "long"
    return None


def _summary(*, details: dict[str, Any], length_tag: str | None) -> str:
    if details["empty"]:
        return "empty plain text file"

    prefix = f"{length_tag} " if length_tag else ""
    if details["is_license"]:
        return f"{prefix}license text file".strip()
    if details["is_log"]:
        return f"{prefix}log-like text file".strip()
    if details["is_config"]:
        return f"{prefix}config-like text file".strip()
    if details["is_readme"]:
        return f"{prefix}readme text file".strip()
    if details["is_notes"]:
        return f"{prefix}plain text note".strip()
    return f"{prefix}plain text file".strip()


def _original_filename(file_info: dict[str, Any] | None) -> str:
    if not file_info:
        return ""
    return str(file_info.get("original_filename") or "")


def _extension(file_info: dict[str, Any] | None) -> str:
    if not file_info:
        return ""
    return str(file_info.get("extension") or "").lower()


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
