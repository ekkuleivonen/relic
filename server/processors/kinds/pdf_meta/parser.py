"""PDF parser. Returns a discovery payload for the pdf_meta section."""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from typing import Any

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError
from pypdf.generic import DictionaryObject, IndirectObject

from domain.files.meta import build_parser_discovery, empty_parser_discovery
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_MAX_TEXT_KEYWORDS = 20
_MAX_TEXT_CHARS = 2000
_MEANINGLESS_METADATA_TERMS = {
    "adobe",
    "acrobat",
    "microsoft",
    "word",
    "pages",
    "preview",
    "quartz",
    "pypdf",
}


def empty_pdf_meta() -> dict[str, Any]:
    """Discovery payload for failed or unavailable PDF parsing."""
    return empty_parser_discovery(tags=["pdf", "document"])


def parse_pdf(*, content: bytes) -> dict[str, Any]:
    """Parse PDF bytes into a discovery payload. Never raises."""
    if not content:
        return empty_pdf_meta()
    try:
        return parse(content)
    except (PdfReadError, FileNotDecryptedError, OSError, ValueError) as exc:
        log.warning("pdf_parse_failed", error=str(exc))
        return empty_pdf_meta()
    except Exception as exc:
        log.warning("pdf_parse_failed", error=str(exc))
        return empty_pdf_meta()


def parse(content: bytes) -> dict[str, Any]:
    """Parse PDF bytes into the common discovery payload."""
    reader = PdfReader(io.BytesIO(content), strict=False)

    details: dict[str, Any] = {
        "encrypted": bool(reader.is_encrypted),
        "page_count": None,
        "metadata_keywords": [],
        "text_keywords": [],
        "has_text": False,
        "has_images": False,
        "has_form": False,
        "signed": False,
    }

    if reader.is_encrypted and not _decrypt_empty_password(reader):
        return _build_discovery(details)

    _extract_reader_details(reader, details)
    return _build_discovery(details)


def _extract_reader_details(reader: PdfReader, details: dict[str, Any]) -> None:
    try:
        pages = list(reader.pages)
    except FileNotDecryptedError:
        return

    details["page_count"] = len(pages)
    details["metadata_keywords"] = _metadata_keywords(reader.metadata)
    details["has_form"] = _has_form(reader)
    details["signed"] = _is_signed(reader)

    if not pages:
        return

    first_page = pages[0]
    text = _safe_extract_text(first_page)
    details["has_text"] = bool(text.strip())
    details["text_keywords"] = _text_keywords(text)
    details["has_images"] = any(_page_has_images(page) for page in pages[:5])


def _build_discovery(details: dict[str, Any]) -> dict[str, Any]:
    page_count = details.get("page_count")
    tags: list[str | None] = ["pdf", "document"]
    if details.get("encrypted"):
        tags.append("encrypted")
    if details.get("has_text"):
        tags.append("has-text")
    if details.get("has_images"):
        tags.append("has-images")
    if _is_scanned(details):
        tags.append("scanned")
    if details.get("has_form"):
        tags.append("form")
    if details.get("signed"):
        tags.append("signed")

    length_tag = _length_tag(page_count)
    if length_tag:
        tags.append(length_tag)

    keywords = _dedupe(
        [
            *details.get("metadata_keywords", []),
            *details.get("text_keywords", []),
        ],
        limit=_MAX_KEYWORDS,
    )

    kvs: dict[str, Any] = {}
    if page_count is not None:
        kvs["page_count"] = page_count

    summary = _summary(details=details, length_tag=length_tag)
    return build_parser_discovery(
        tags=_dedupe(tags, limit=12),
        keywords=keywords,
        summary=summary,
        kvs=kvs,
    )


def _metadata_keywords(metadata: Any) -> list[str]:
    if not metadata:
        return []

    values = [
        getattr(metadata, "title", None),
        getattr(metadata, "author", None),
        getattr(metadata, "subject", None),
    ]

    producer = getattr(metadata, "producer", None)
    creator = getattr(metadata, "creator", None)
    values.extend(
        value
        for value in [producer, creator]
        if value and not _is_generic_generator(value)
    )
    return _dedupe(values, limit=10)


def _is_generic_generator(value: str) -> bool:
    normalized = _normalize_keyword(value)
    if not normalized:
        return True
    words = set(re.split(r"[^a-z0-9]+", normalized))
    return bool(words & _MEANINGLESS_METADATA_TERMS)


def _safe_extract_text(page: Any) -> str:
    try:
        return (page.extract_text() or "")[:_MAX_TEXT_CHARS]
    except Exception:
        return ""


def _text_keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
    return _dedupe(words, limit=_MAX_TEXT_KEYWORDS)


def _has_form(reader: PdfReader) -> bool:
    try:
        root = _resolve(reader.trailer.get("/Root"))
        return isinstance(root, dict) and bool(root.get("/AcroForm"))
    except Exception:
        return False


def _is_signed(reader: PdfReader) -> bool:
    try:
        fields = reader.get_fields() or {}
    except Exception:
        return False
    for field in fields.values():
        field_type = field.get("/FT") if isinstance(field, dict) else None
        if str(field_type) == "/Sig":
            return True
    return False


def _page_has_images(page: Any) -> bool:
    try:
        resources = _resolve(page.get("/Resources"))
        if not isinstance(resources, dict):
            return False
        xobjects = _resolve(resources.get("/XObject"))
        if not isinstance(xobjects, dict):
            return False
        return any(_is_image_xobject(obj) for obj in xobjects.values())
    except Exception:
        return False


def _is_image_xobject(obj: Any) -> bool:
    resolved = _resolve(obj)
    if not isinstance(resolved, DictionaryObject | dict):
        return False
    return str(resolved.get("/Subtype")) == "/Image"


def _resolve(value: Any) -> Any:
    if isinstance(value, IndirectObject):
        return value.get_object()
    return value


def _decrypt_empty_password(reader: PdfReader) -> bool:
    try:
        return bool(reader.decrypt(""))
    except Exception:
        return False


def _is_scanned(details: dict[str, Any]) -> bool:
    return (
        bool(details.get("page_count"))
        and details.get("has_images")
        and not details.get("has_text")
    )


def _length_tag(page_count: int | None) -> str | None:
    if page_count is None:
        return None
    if page_count <= 3:
        return "short"
    if page_count >= 50:
        return "long"
    return None


def _summary(*, details: dict[str, Any], length_tag: str | None) -> str:
    if details.get("encrypted"):
        return "encrypted PDF document"
    if _is_scanned(details):
        return "scanned PDF document"
    if details.get("has_form"):
        return "PDF form document"
    if details.get("signed"):
        return "signed PDF document"
    if details.get("has_text"):
        prefix = f"{length_tag} " if length_tag else ""
        return f"{prefix}text PDF document".strip()
    prefix = f"{length_tag} " if length_tag else ""
    return f"{prefix}PDF document".strip()


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
