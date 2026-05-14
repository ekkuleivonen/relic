"""HTML parser. Writes compact discovery metadata into file meta."""

from __future__ import annotations

import html
import html.parser
import json
import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from charset_normalizer import from_bytes

from domain.files.meta import build_file_meta, build_parser_meta
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_MAX_VISIBLE_TEXT_CHARS = 8000
_MAX_HEADINGS = 12
_SCRIPT_HEAVY_MIN_SCRIPTS = 8
_SCRIPT_HEAVY_RATIO = 0.12  # scripts per KB of visible text

_HTML_MIME = "text/html"


def empty_html_meta(*, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=["html", "webpage"],
        keywords=[],
        kvs={},
    )


def parse_html(*, content: bytes, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse HTML bytes for storage in file meta. Never raises."""
    if not content:
        return empty_html_meta(existing_meta=existing_meta)
    try:
        return parse(content, existing_meta=existing_meta)
    except Exception as exc:
        log.warning("html_parse_failed", error=str(exc))
        return empty_html_meta(existing_meta=existing_meta)


def parse(content: bytes, *, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    text = _decode_html(content)
    details = _HtmlExtractor().extract(text)
    return _build_discovery_meta(details=details, existing_meta=existing_meta)


class _HtmlExtractor(html.parser.HTMLParser):
    """Lightweight SAX-style harvest; skips script/style except JSON-LD."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._headings: list[str] = []
        self._visible_parts: list[str] = []
        self._heading_buf: list[str] = []
        self._heading_tag: str | None = None
        self._lang: str | None = None
        self._title: str | None = None
        self._meta_desc: str | None = None
        self._og_title: str | None = None
        self._og_desc: str | None = None
        self._og_type: str | None = None
        self._canonical: str | None = None
        self._in_skip = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._collect_ld_json = False
        self._ld_chunks: list[str] = []
        self._article_depth = 0
        self._saw_article = False
        self._img_count = 0
        self._script_count = 0
        self._form_count = 0
        self._link_count = 0
        self._external_link_count = 0
        self._ld_scripts: list[str] = []

    def extract(self, html_text: str) -> dict[str, Any]:
        self.feed(html_text)
        self.close()
        visible = " ".join(self._visible_parts)
        ld_types: list[str] = []
        for chunk in self._ld_scripts:
            ld_types.extend(_extract_json_ld_types(chunk))

        og_type_norm_raw = (_normalize_keyword(self._og_type) or "").replace(" ", "-")

        ld_types_lc = [t.lower() for t in ld_types]
        og_type_norm_lc = og_type_norm_raw.lower() if og_type_norm_raw else ""

        tags_article = bool(self._saw_article)
        if og_type_norm_lc == "article":
            tags_article = True
        if "article" in ld_types_lc:
            tags_article = True

        is_landing = False
        if "landingpage" in ld_types_lc or "faqpage" in ld_types_lc:
            is_landing = True
        if "webpage" in ld_types_lc or "website" in ld_types_lc:
            landing_words = {"landing", "homepage", "product", "trial", "signup", "pricing"}
            blob = " ".join(
                v
                for v in (
                    self._title,
                    self._meta_desc,
                    self._og_title,
                    self._og_desc,
                )
                if v
            ).lower()
            if blob and any(w in blob for w in landing_words):
                is_landing = True
        blob_title = (self._title or "").lower()
        blob_desc = (self._meta_desc or "").lower()
        blob_og = (self._og_title or "").lower()
        if "landing page" in blob_title or "landing page" in blob_desc or "landing" in blob_og:
            is_landing = True

        visible_len = max(len(visible.encode("utf-8")), 1)
        script_ratio = self._script_count / (visible_len / 1024.0)

        return {
            "lang": self._lang,
            "title": _clean_text(self._title),
            "meta_description": _clean_text(self._meta_desc),
            "og_title": _clean_text(self._og_title),
            "og_description": _clean_text(self._og_desc),
            "og_type": og_type_norm_raw or None,
            "canonical_domain": _canonical_domain(self._canonical),
            "canonical_url": self._canonical,
            "headings": [_clean_text(h) for h in self._headings if h],
            "visible_sample": visible[:_MAX_VISIBLE_TEXT_CHARS],
            "img_count": self._img_count,
            "script_count": self._script_count,
            "form_count": self._form_count,
            "link_count": self._link_count,
            "external_link_count": self._external_link_count,
            "tags_article": tags_article,
            "tags_landing": is_landing,
            "script_heavy": self._script_count >= _SCRIPT_HEAVY_MIN_SCRIPTS
            or script_ratio >= _SCRIPT_HEAVY_RATIO,
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): v for k, v in attrs if k}
        lowered = tag.lower()

        if lowered == "html" and attrs_dict.get("lang"):
            self._lang = (attrs_dict.get("lang") or "").strip().lower() or self._lang

        if lowered == "script":
            self._script_count += 1
            self._in_skip += 1
            ctype = (attrs_dict.get("type") or "").lower()
            if "ld+json" in ctype or ctype == "application/json":
                self._collect_ld_json = True
                self._ld_chunks = []
            else:
                self._collect_ld_json = False
            return

        if lowered in {"style", "noscript", "template"}:
            self._in_skip += 1
            return

        if lowered == "title":
            self._in_title = True
            self._title_parts = []
            return

        if lowered == "meta":
            name = (attrs_dict.get("name") or "").lower()
            prop = (attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content")
            if not content:
                return
            if name == "description":
                self._meta_desc = content
                return
            if prop == "og:title":
                self._og_title = content
            elif prop == "og:description":
                self._og_desc = content
            elif prop == "og:type":
                self._og_type = content
            return

        if lowered == "link" and (attrs_dict.get("rel") or "").lower() == "canonical":
            href = attrs_dict.get("href")
            if href:
                self._canonical = href.strip()
            return

        if lowered == "article":
            self._article_depth += 1
            self._saw_article = True

        if lowered == "img":
            self._img_count += 1

        if lowered == "form":
            self._form_count += 1

        if lowered == "a" and attrs_dict.get("href") is not None:
            href = attrs_dict["href"]
            if _is_countable_anchor_href(href):
                self._link_count += 1
                if _is_external_http_url(href):
                    self._external_link_count += 1

        if lowered in {"h1", "h2", "h3"} and len(self._headings) < _MAX_HEADINGS:
            self._heading_tag = lowered
            self._heading_buf = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()

        if lowered == "script":
            if self._collect_ld_json:
                joined = "".join(self._ld_chunks).strip()
                if joined:
                    self._ld_scripts.append(joined)
                self._collect_ld_json = False
                self._ld_chunks = []
            self._in_skip -= 1
            return

        if lowered in {"style", "noscript", "template"}:
            self._in_skip -= 1
            return

        if lowered == "title" and self._in_title:
            self._in_title = False
            self._title = "".join(self._title_parts).strip() or self._title
            self._title_parts = []

        if lowered == "article" and self._article_depth > 0:
            self._article_depth -= 1

        if lowered in {"h1", "h2", "h3"}:
            heading = "".join(self._heading_buf).strip()
            if heading and len(self._headings) < _MAX_HEADINGS:
                self._headings.append(html.unescape(heading))
            self._heading_tag = None
            self._heading_buf = []

    def handle_data(self, data: str) -> None:
        if self._collect_ld_json and self._in_skip > 0:
            self._ld_chunks.append(data)
            return

        if self._in_title:
            self._title_parts.append(data)
            return

        if self._heading_tag and self._in_skip <= 0:
            self._heading_buf.append(data)

        if self._in_skip > 0:
            return

        stripped = html.unescape(data).strip()
        if stripped:
            self._visible_parts.append(stripped)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def _build_discovery_meta(
    *, details: dict[str, Any], existing_meta: dict[str, Any] | None
) -> dict[str, Any]:
    tags: list[str | None] = ["html", "webpage"]

    if details["tags_article"]:
        tags.append("article")
    if details["tags_landing"]:
        tags.append("landing-page")
    if details["form_count"]:
        tags.append("form")
    if details["img_count"]:
        tags.append("has-images")
    if details["external_link_count"]:
        tags.append("external-links")
    if details["script_heavy"]:
        tags.append("script-heavy")

    canonical_domain = details["canonical_domain"]
    keywords = _dedupe(
        [
            canonical_domain,
            details["lang"],
            details["title"],
            details["meta_description"],
            details["og_title"],
            details["og_description"],
            *details["headings"],
            *_tokenize(details["visible_sample"]),
            *(_filename_terms(existing_meta)),
        ],
        limit=_MAX_KEYWORDS,
    )

    kvs: dict[str, Any] = {}
    if details["link_count"]:
        kvs["link_count"] = details["link_count"]
    if details["external_link_count"]:
        kvs["external_link_count"] = details["external_link_count"]
    if details["img_count"]:
        kvs["image_count"] = details["img_count"]
    if details["script_count"]:
        kvs["script_count"] = details["script_count"]

    summary = _summary(details=details, tags_article=details["tags_article"])

    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=_dedupe(tags, limit=12),
        keywords=keywords,
        summary=summary,
        kvs=kvs,
        mimetype=_HTML_MIME,
    )


def _summary(*, details: dict[str, Any], tags_article: bool) -> str:
    chunk = ""
    for key in ("title", "og_title", "meta_description", "og_description"):
        val = details.get(key)
        if val:
            chunk = val
            break
    if tags_article:
        if chunk:
            return f"HTML article webpage: {chunk[:120]}"
        return "HTML article webpage"
    if details["tags_landing"]:
        return "script-heavy landing HTML page" if details["script_heavy"] else "HTML landing webpage"
    if details["script_heavy"]:
        return "script-heavy HTML webpage"
    if chunk:
        return f"HTML webpage: {chunk[:120]}"
    return "HTML webpage"


def _decode_html(content: bytes) -> str:
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

    detected = from_bytes(content).best()
    if detected and detected.encoding:
        return content.decode(detected.encoding, errors="replace")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="replace")


def _canonical_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.split("@")[-1].split(":")[0].lower().strip(".")
    return host or None


def _is_countable_anchor_href(href: str | None) -> bool:
    """True for anchors with a non-empty href (including #fragment and relative URLs)."""
    if href is None:
        return False
    return bool(href.strip())


def _is_external_http_url(href: str | None) -> bool:
    if not href or href.startswith("#") or href.startswith("mailto:"):
        return False
    lowered = href.lower().strip()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    t = html.unescape(value)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def _tokenize(sample: str) -> list[str]:
    return [
        tok.lower()
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", sample)
        if len(tok) <= 48
    ][:25]


def _filename_terms(existing_meta: dict[str, Any] | None) -> list[str]:
    fn = ""
    if existing_meta:
        fn = str(existing_meta.get("original_filename") or "")
    stem = PurePosixPath(fn).stem.lower()
    return [
        w
        for w in re.split(r"[^a-z0-9]+", stem)
        if len(w) >= 3 and w not in {"htm", "html", "www"}
    ][:5]


def _extract_json_ld_types(raw: str) -> list[str]:
    types: list[str] = []
    trimmed = raw.strip()
    blobs = [trimmed]
    if not trimmed.startswith("{"):
        start = trimmed.find("{")
        if start >= 0:
            blobs.append(trimmed[start:])

    for blob in blobs:
        blob = blob.strip()
        if not blob.startswith("{"):
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        types.extend(_types_from_json_ld_node(data))

    normed: list[str] = []
    for t in types:
        tn = _normalize_keyword(str(t).replace("/", " "))
        if tn:
            normed.append(tn.replace(" ", ""))
    seen: set[str] = set()
    out: list[str] = []
    for t in normed:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _types_from_json_ld_node(node: Any) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str):
            out.append(t.split("/")[-1])
        elif isinstance(t, list):
            for item in t:
                if isinstance(item, str):
                    out.append(item.split("/")[-1])
        for v in node.values():
            out.extend(_types_from_json_ld_node(v))
    elif isinstance(node, list):
        for item in node:
            out.extend(_types_from_json_ld_node(item))
    return out


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
