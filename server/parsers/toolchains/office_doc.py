"""Office document parser. Writes compact discovery metadata into file meta."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from typing import Any
from xml.etree import ElementTree

from file_meta import build_file_meta, build_parser_meta
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_WORD_EXTENSIONS = {"doc", "docx", "odt", "rtf"}
_DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ODT_MIMETYPE = "application/vnd.oasis.opendocument.text"


def empty_office_doc_meta(*, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shape matching parse() output for failed or unavailable office parsing."""
    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=["document", "word-document"],
        keywords=[],
        kvs={},
    )


def parse_office_doc(
    *, content: bytes, existing_meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse office document bytes for storage in file meta. Never raises."""
    if not content:
        return empty_office_doc_meta(existing_meta=existing_meta)
    try:
        return parse(content, existing_meta=existing_meta)
    except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        log.warning("office_doc_parse_failed", error=str(exc))
        return empty_office_doc_meta(existing_meta=existing_meta)
    except Exception as exc:
        log.warning("office_doc_parse_failed", error=str(exc))
        return empty_office_doc_meta(existing_meta=existing_meta)


def parse(content: bytes, *, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse DOCX, ODT, and RTF bytes into the common discovery meta dict."""
    extension = _extension(existing_meta)
    if extension == "docx" or _looks_like_docx(content):
        details = _parse_docx(content)
    elif extension == "odt" or _looks_like_odt(content):
        details = _parse_odt(content)
    elif extension == "rtf" or content.lstrip().startswith(b"{\\rtf"):
        details = _parse_rtf(content)
    else:
        raise ValueError("Unsupported office document")
    return _build_discovery_meta(details=details, existing_meta=existing_meta)


def _parse_docx(content: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        core = _xml_root(archive, "docProps/core.xml")
        app = _xml_root(archive, "docProps/app.xml")
        document = _xml_root(archive, "word/document.xml")
        comments_present = "word/comments.xml" in archive.namelist()
        names = set(archive.namelist())

    headings = _docx_headings(document)
    text = " ".join(_xml_text(document))
    return {
        "format": "docx",
        "title": _first_text(core, "title"),
        "author": _first_text(core, "creator"),
        "subject": _first_text(core, "subject"),
        "headings": headings,
        "text": text,
        "word_count": _int_text(app, "Words") or _word_count(text),
        "page_count": _int_text(app, "Pages"),
        "has_images": any(name.startswith("word/media/") for name in names)
        or "drawing" in _element_names(document),
        "has_tables": "tbl" in _element_names(document),
        "has_comments": comments_present,
        "tracked_changes": bool({"ins", "del"} & _element_names(document)),
    }


def _parse_odt(content: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        meta = _xml_root(archive, "meta.xml")
        document = _xml_root(archive, "content.xml")
        names = set(archive.namelist())

    headings = _texts_for_local_names(document, {"h"})
    text = " ".join(_xml_text(document))
    return {
        "format": "odt",
        "title": _first_text(meta, "title"),
        "author": _first_text(meta, "creator"),
        "subject": _first_text(meta, "subject"),
        "headings": headings,
        "text": text,
        "word_count": _odt_stat(meta, "word-count") or _word_count(text),
        "page_count": _odt_stat(meta, "page-count"),
        "has_images": any(name.startswith("Pictures/") for name in names) or "image" in _element_names(document),
        "has_tables": "table" in _element_names(document),
        "has_comments": "annotation" in _element_names(document),
        "tracked_changes": "changed-region" in _element_names(document),
    }


def _parse_rtf(content: bytes) -> dict[str, Any]:
    text = _rtf_to_text(content.decode("latin-1", errors="replace"))
    return {
        "format": "rtf",
        "title": None,
        "author": None,
        "subject": None,
        "headings": [],
        "text": text,
        "word_count": _word_count(text),
        "page_count": None,
        "has_images": "\\pict" in text,
        "has_tables": False,
        "has_comments": False,
        "tracked_changes": False,
    }


def _build_discovery_meta(
    *, details: dict[str, Any], existing_meta: dict[str, Any] | None
) -> dict[str, Any]:
    type_tags = _type_tags(details=details, existing_meta=existing_meta)
    tags: list[str | None] = ["document", "word-document", *type_tags]
    if details["has_images"]:
        tags.append("has-images")
    if details["has_tables"]:
        tags.append("has-tables")
    if details["has_comments"]:
        tags.append("has-comments")
    if details["tracked_changes"]:
        tags.append("tracked-changes")

    keywords = _dedupe(
        [
            details["title"],
            details["author"],
            details["subject"],
            *details["headings"],
            *type_tags,
        ],
        limit=_MAX_KEYWORDS,
    )

    kvs: dict[str, Any] = {}
    if details["word_count"] is not None:
        kvs["word_count"] = details["word_count"]
    if details["page_count"] is not None:
        kvs["page_count"] = details["page_count"]

    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=_dedupe(tags, limit=12),
        keywords=keywords,
        summary=_summary(type_tags=type_tags, details=details),
        kvs=kvs,
        mimetype=_mimetype_for_format(details["format"]),
    )


def _xml_root(archive: zipfile.ZipFile, name: str) -> ElementTree.Element | None:
    if name not in archive.namelist():
        return None
    return ElementTree.fromstring(archive.read(name))


def _docx_headings(root: ElementTree.Element | None) -> list[str]:
    if root is None:
        return []
    headings: list[str] = []
    for paragraph in root.iter():
        if _local_name(paragraph.tag) != "p":
            continue
        style = None
        for child in paragraph.iter():
            if _local_name(child.tag) == "pStyle":
                style = child.attrib.get(_namespaced("val")) or child.attrib.get("val")
                break
        if style and style.lower().startswith("heading"):
            text = " ".join(_xml_text(paragraph))
            if text:
                headings.append(text)
    return _dedupe(headings, limit=12)


def _first_text(root: ElementTree.Element | None, local_name: str) -> str | None:
    if root is None:
        return None
    for element in root.iter():
        if _local_name(element.tag) == local_name and element.text:
            return element.text.strip() or None
    return None


def _texts_for_local_names(root: ElementTree.Element | None, names: set[str]) -> list[str]:
    if root is None:
        return []
    values: list[str] = []
    for element in root.iter():
        if _local_name(element.tag) in names:
            text = " ".join(_xml_text(element))
            if text:
                values.append(text)
    return _dedupe(values, limit=12)


def _xml_text(root: ElementTree.Element | None) -> list[str]:
    if root is None:
        return []
    return [text.strip() for text in root.itertext() if text and text.strip()]


def _element_names(root: ElementTree.Element | None) -> set[str]:
    if root is None:
        return set()
    return {_local_name(element.tag) for element in root.iter()}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespaced(local_name: str) -> str:
    return f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{local_name}"


def _int_text(root: ElementTree.Element | None, local_name: str) -> int | None:
    text = _first_text(root, local_name)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _odt_stat(root: ElementTree.Element | None, name: str) -> int | None:
    if root is None:
        return None
    for element in root.iter():
        if _local_name(element.tag) != "document-statistic":
            continue
        for key, value in element.attrib.items():
            if _local_name(key) != name:
                continue
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _rtf_to_text(value: str) -> str:
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", value)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = text.replace("\\", " ")
    return re.sub(r"\s+", " ", text).strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text))


def _type_tags(*, details: dict[str, Any], existing_meta: dict[str, Any] | None) -> list[str]:
    observed = " ".join(
        value
        for value in [
            _original_filename(existing_meta),
            details["title"],
            details["subject"],
            *details["headings"],
            details["text"][:500],
        ]
        if value
    ).lower()
    tags: list[str] = []
    if "report" in observed:
        tags.append("report")
    if "letter" in observed:
        tags.append("letter")
    if "contract" in observed:
        tags.append("contract")
    return tags


def _summary(*, type_tags: list[str], details: dict[str, Any]) -> str:
    role = type_tags[0] if type_tags else None
    structures = []
    if details["has_tables"]:
        structures.append("tables")
    if details["has_images"]:
        structures.append("images")
    if details["has_comments"]:
        structures.append("comments")
    if details["tracked_changes"]:
        structures.append("tracked changes")
    base = "word document"
    if role:
        base = f"{base} {role}"
    if not structures:
        return base
    return f"{base} with {_join_words(structures)}"


def _join_words(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _looks_like_docx(content: bytes) -> bool:
    if not content.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def _looks_like_odt(content: bytes) -> bool:
    if not content.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return archive.read("mimetype") == b"application/vnd.oasis.opendocument.text"
    except (KeyError, zipfile.BadZipFile):
        return False


def _mimetype_for_format(format_name: str) -> str | None:
    if format_name == "docx":
        return _DOCX_MIMETYPE
    if format_name == "odt":
        return _ODT_MIMETYPE
    if format_name == "rtf":
        return "application/rtf"
    return None


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
