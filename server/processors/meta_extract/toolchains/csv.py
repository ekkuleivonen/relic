"""CSV parser. Writes compact discovery metadata under the ``csv`` key.

Robust against real-world CSV: delimiters, encodings, quotes, headers, preamble
rows, and non-Western text (including Japanese).
"""

from __future__ import annotations

import codecs
import csv
import io
import re
import unicodedata
from datetime import datetime
from typing import IO, Any

from charset_normalizer import from_bytes
from file_meta import build_file_meta, build_parser_meta
from utils.logging import get_logger

log = get_logger(__name__)

_HEAD_BYTES = 64 * 1024
_TYPE_SAMPLE_ROWS = 1000
_CANDIDATE_DELIMITERS = ",;\t|"
_MAX_KEYWORDS = 50

# How many leading rows to consider skipping when looking for the actual
# CSV body. Real-world exports often have comment lines, blank rows, or
# a summary preamble before the data starts.
_MAX_SKIP_PROBE_ROWS = 8

# Encoding detection: Japanese encodings are unusually common and
# charset-normalizer often misidentifies them. We score candidates by
# Japanese character density to pick the right one when in doubt.
_JAPANESE_ENCODING_PRIORITY = ("cp932", "shift_jis", "euc_jp", "iso2022_jp")
_STRICT_FALLBACK_ENCODINGS = _JAPANESE_ENCODING_PRIORITY
_MAX_DETECTOR_MATCHES = 8
_ENCODING_ALIASES = {
    "ascii": "utf-8",
    "iso8859-1": "latin-1",
}

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
]

_BOOLEAN_TRUE = {"true", "t", "yes", "y", "1"}
_BOOLEAN_FALSE = {"false", "f", "no", "n", "0"}


def empty_csv_meta(*, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shape matching parse() output for failed or unavailable CSV parsing."""
    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(existing=base_meta, tags=["data"], keywords=[], kvs={})


def parse_csv(*, content: bytes, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Entry point for the parser worker. Swallows unexpected errors."""
    try:
        return parse(content, existing_meta=existing_meta)
    except Exception as exc:
        log.warning("csv_parse_failed", error=str(exc))
        return empty_csv_meta(existing_meta=existing_meta)


def parse(
    content: bytes | IO[bytes], *, existing_meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse CSV bytes (or stream) into the common discovery meta dict."""
    details: dict[str, Any] = {
        "row_count": None,
        "column_count": None,
        "columns": None,
        "column_types": None,
        "delimiter": None,
        "quote_char": None,
        "has_header": None,
        "encoding": None,
        "line_terminator": None,
        "skipped_prefix_rows": None,
        "empty_cells_pct": None,
    }

    if isinstance(content, bytes):
        full_bytes = content
    else:
        full_bytes = content.read()

    if not full_bytes:
        details["row_count"] = 0
        details["column_count"] = 0
        details["columns"] = []
        details["column_types"] = {}
        details["empty_cells_pct"] = 0.0
        return _build_discovery_meta(details, existing_meta=existing_meta)

    encoding = _detect_encoding(full_bytes)
    details["encoding"] = encoding

    details["line_terminator"] = _detect_line_terminator(full_bytes[:_HEAD_BYTES])

    try:
        text = full_bytes.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        text = full_bytes.decode("latin-1", errors="replace")
        details["encoding"] = "latin-1"

    dialect, has_header, skip_prefix = _detect_dialect(text)
    details["delimiter"] = dialect.delimiter
    details["quote_char"] = (
        dialect.quotechar if dialect.quoting != csv.QUOTE_NONE else None
    )
    details["has_header"] = has_header
    details["skipped_prefix_rows"] = skip_prefix

    _extract_rows(text, dialect, has_header, skip_prefix, details)

    return _build_discovery_meta(details, existing_meta=existing_meta)


def _build_discovery_meta(
    details: dict[str, Any], *, existing_meta: dict[str, Any] | None
) -> dict[str, Any]:
    row_count = details.get("row_count")
    column_count = details.get("column_count")
    columns = details.get("columns") or []
    column_types = details.get("column_types") or {}

    tags = ["data"]
    if row_count == 0 or column_count == 0:
        tags.append("empty")
    else:
        tags.append("table")
    if column_count and column_count >= 50:
        tags.append("wide")
    if row_count and row_count >= 10_000:
        tags.append("tall")

    keywords = _dedupe(
        [
            *[column for column in columns if not _is_generated_column(column)],
            *[column_types[column] for column in columns if column in column_types],
        ],
        limit=_MAX_KEYWORDS,
    )

    kvs: dict[str, Any] = {}
    if row_count is not None:
        kvs["row_count"] = row_count
    if column_count is not None:
        kvs["column_count"] = column_count

    summary = _csv_summary(row_count=row_count, column_count=column_count)

    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=tags,
        keywords=keywords,
        summary=summary,
        kvs=kvs,
    )


def _csv_summary(*, row_count: int | None, column_count: int | None) -> str | None:
    if row_count is None or column_count is None:
        return None
    if row_count == 0 or column_count == 0:
        return "empty CSV table"
    return f"CSV table with {row_count} rows and {column_count} columns"


def _dedupe(values: list[str | None], *, limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        keyword = _normalize_keyword(value)
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
        if len(result) >= limit:
            break
    return result


def _normalize_keyword(value: str | None) -> str | None:
    if value is None:
        return None
    keyword = re.sub(r"\s+", " ", str(value).strip().lower())
    return keyword or None


def _is_generated_column(column: str) -> bool:
    return re.fullmatch(r"col_\d+", column) is not None


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def _detect_encoding(content: bytes) -> str:
    """Detect the file's encoding. Tries fast paths before the slower detector."""
    bom_encoding = _detect_bom_encoding(content)
    if bom_encoding is not None:
        return bom_encoding

    if _try_decode(content, "utf-8") is not None:
        return "utf-8"

    detected = _detect_encoding_with_normalizer(content)
    if detected is not None:
        return detected

    for encoding in _STRICT_FALLBACK_ENCODINGS:
        if _try_decode(content, encoding) is not None:
            return encoding

    return "latin-1"


def _detect_bom_encoding(content: bytes) -> str | None:
    if content.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if content.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32-le"
    if content.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32-be"
    if content.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if content.startswith(b"\xfe\xff"):
        return "utf-16-be"
    return None


def _detect_encoding_with_normalizer(content: bytes) -> str | None:
    """Use charset-normalizer with Japanese-aware tiebreaking.

    charset-normalizer often picks generic codecs (e.g. cp1252) when a
    Japanese codec would be the right answer. We score candidates by
    actual Japanese character density to break ties correctly.
    """
    sample = content[:_HEAD_BYTES]

    # (encoding, language, japanese_score, detector_rank)
    candidates: list[tuple[str, str, int, int]] = []
    seen: set[str] = set()

    for rank, match in enumerate(from_bytes(sample)):
        if rank >= _MAX_DETECTOR_MATCHES:
            break
        encoding = _canonicalize_encoding(match.encoding)
        if encoding is None or encoding in seen:
            continue
        decoded = _try_decode(content, encoding)
        if decoded is None:
            continue
        seen.add(encoding)
        candidates.append(
            (
                encoding,
                match.language or "Unknown",
                _japanese_character_score(decoded),
                rank,
            )
        )

    if not candidates:
        return None

    # Prefer Japanese encodings when the decoded text has Japanese characters,
    # even if the detector ranked another encoding higher.
    japanese = [
        c
        for c in candidates
        if c[0] in _JAPANESE_ENCODING_PRIORITY and (c[1] == "Japanese" or c[2] > 0)
    ]
    if japanese:
        japanese.sort(
            key=lambda c: (
                c[1] == "Japanese",
                c[2],
                -_JAPANESE_ENCODING_PRIORITY.index(c[0]),
                -c[3],
            ),
            reverse=True,
        )
        return japanese[0][0]

    return candidates[0][0]


def _canonicalize_encoding(encoding: str | None) -> str | None:
    if not encoding:
        return None
    try:
        normalized = codecs.lookup(encoding).name
    except LookupError:
        return None
    return _ENCODING_ALIASES.get(normalized, normalized)


def _try_decode(content: bytes, encoding: str) -> str | None:
    try:
        return content[:_HEAD_BYTES].decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None


def _japanese_character_score(text: str) -> int:
    """Count hiragana, katakana, and halfwidth katakana characters.

    Used to disambiguate when the detector is uncertain between Japanese
    and non-Japanese codecs. CJK ideographs are excluded because they
    overlap heavily with Chinese, which would muddy the signal.
    """
    score = 0
    for char in text:
        codepoint = ord(char)
        if 0x3040 <= codepoint <= 0x30FF or 0xFF66 <= codepoint <= 0xFF9F:
            score += 1
    return score


# ---------------------------------------------------------------------------
# Line terminator
# ---------------------------------------------------------------------------


def _detect_line_terminator(head: bytes) -> str | None:
    crlf = head.count(b"\r\n")
    lf = head.count(b"\n") - crlf
    cr = head.count(b"\r") - crlf

    if crlf == 0 and lf == 0 and cr == 0:
        return None

    counts = {"\r\n": crlf, "\n": lf, "\r": cr}
    return max(counts, key=lambda k: counts[k])


# ---------------------------------------------------------------------------
# Dialect detection
# ---------------------------------------------------------------------------


def _detect_dialect(text: str) -> tuple[csv.Dialect, bool, int]:
    """Detect dialect, header presence, and how many leading rows to skip.

    Real-world CSVs often have leading metadata: comment lines, summary
    rows, blank lines. We try sniffing with progressively more rows
    skipped and pick the configuration that produces the most consistent
    row widths (which is what a well-formed CSV body looks like).

    Returns (dialect, has_header, skip_prefix_rows).
    """
    sniffer = csv.Sniffer()
    lines = text.splitlines()

    if not lines:
        return csv.excel, False, 0

    best: tuple[int, csv.Dialect, str] | None = None
    best_score = (-1, -1)

    max_skip = min(_MAX_SKIP_PROBE_ROWS, max(0, len(lines) - 1))
    for skip in range(max_skip + 1):
        body_lines = [ln for ln in lines[skip:] if ln.strip()]
        if len(body_lines) < 2:
            continue
        sample = "\n".join(body_lines[:12])
        try:
            dialect = sniffer.sniff(sample, delimiters=_CANDIDATE_DELIMITERS)
        except csv.Error:
            continue
        widths = _row_widths(body_lines[:12], dialect)
        if not widths:
            continue
        max_width = max(widths)
        if max_width <= 1:
            continue
        stable_rows = sum(1 for w in widths if w == max_width)
        score = (max_width, stable_rows)
        if score > best_score:
            best = (skip, dialect, sample)
            best_score = score

    if best is None:
        return csv.excel, True, 0

    skip_prefix, dialect, sample = best

    try:
        has_header = sniffer.has_header(sample)
    except csv.Error:
        has_header = _heuristic_has_header(sample, dialect)

    return dialect, has_header, skip_prefix


def _row_widths(lines: list[str], dialect: csv.Dialect) -> list[int]:
    widths: list[int] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = next(csv.reader([line], dialect=dialect))
        except csv.Error:
            continue
        widths.append(len(row))
    return widths


def _heuristic_has_header(sample: str, dialect: csv.Dialect) -> bool:
    """Fallback when Sniffer.has_header fails."""
    try:
        reader = csv.reader(io.StringIO(sample), dialect=dialect)
        first = next(reader, None)
        second = next(reader, None)
    except csv.Error:
        return False

    if not first or not second or len(first) != len(second):
        return False

    first_all_text = all(not _looks_numeric(v) for v in first if v)
    second_any_numeric = any(_looks_numeric(v) for v in second if v)
    return first_all_text and second_any_numeric


# ---------------------------------------------------------------------------
# Row + type extraction
# ---------------------------------------------------------------------------


def _extract_rows(
    text: str,
    dialect: csv.Dialect,
    has_header: bool,
    skip_prefix: int,
    result: dict[str, Any],
) -> None:
    lines = text.splitlines()
    if skip_prefix > 0:
        lines = lines[skip_prefix:]

    reader = csv.reader(io.StringIO("\n".join(lines)), dialect=dialect)

    columns: list[str] = []
    if has_header:
        try:
            header_row = next(reader)
            columns = _normalize_headers(header_row)
        except (StopIteration, csv.Error):
            has_header = False

    samples: list[list[str]] = []
    row_count = 0
    total_cells = 0
    empty_cells = 0
    max_width = 0

    for row in reader:
        if not row or all(not str(c).strip() for c in row):
            continue

        row_count += 1
        width = len(row)
        max_width = max(max_width, width)

        while len(samples) < width:
            samples.append([])

        for i, cell in enumerate(row):
            total_cells += 1
            if cell == "" or cell is None:
                empty_cells += 1
            elif len(samples[i]) < _TYPE_SAMPLE_ROWS:
                samples[i].append(cell)

    column_count = len(columns) if columns else max_width
    if not columns:
        columns = [f"col_{i + 1}" for i in range(column_count)]
    while len(columns) < max_width:
        columns.append(f"col_{len(columns) + 1}")

    column_types = {
        columns[i]: _infer_type(samples[i]) if i < len(samples) else "string"
        for i in range(column_count)
    }

    result["row_count"] = row_count
    result["column_count"] = column_count
    result["columns"] = columns[:column_count]
    result["column_types"] = column_types
    result["empty_cells_pct"] = (
        round(empty_cells / total_cells * 100, 2) if total_cells else 0.0
    )


def _normalize_headers(raw_headers: list[str]) -> list[str]:
    """Turn raw header strings into stable, DB-safe identifiers.

    Steps:
      - Strip BOM, surrounding whitespace, outer matching quotes
      - NFKC normalize (full-width -> ASCII where applicable)
      - Lowercase, replace non-word chars with underscore, collapse repeats
      - Fall back to col_<n> if a header sanitizes to empty
      - Disambiguate duplicates with _2, _3, ... suffixes
    """
    seen: dict[str, int] = {}
    names: list[str] = []
    for idx, raw in enumerate(raw_headers):
        cleaned = _strip_outer_quotes(raw.strip().removeprefix("\ufeff"))
        normalized = unicodedata.normalize("NFKC", cleaned).lower()
        sanitized = re.sub(r"[^\w]", "_", normalized, flags=re.UNICODE)
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        if not sanitized:
            sanitized = f"col_{idx + 1}"
        count = seen.get(sanitized, 0) + 1
        seen[sanitized] = count
        names.append(sanitized if count == 1 else f"{sanitized}_{count}")
    return names


def _strip_outer_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] in ("'", '"') and s[0] == s[-1]:
        return s[1:-1]
    return s


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------


def _infer_type(samples: list[str]) -> str:
    """Return one of: int, float, bool, date, datetime, string, mixed, empty."""
    if not samples:
        return "empty"

    types_seen: set[str] = set()
    for value in samples:
        v = value.strip()
        if not v:
            continue
        types_seen.add(_classify(v))
        if len(types_seen) > 1 and not types_seen <= {"int", "float"}:
            return "mixed"

    if not types_seen:
        return "empty"
    if types_seen == {"int"}:
        return "int"
    if types_seen <= {"int", "float"}:
        return "float"
    if types_seen == {"bool"}:
        return "bool"
    if types_seen == {"date"}:
        return "date"
    if types_seen == {"datetime"} or types_seen == {"date", "datetime"}:
        return "datetime"
    if types_seen == {"string"}:
        return "string"
    return "mixed"


def _classify(value: str) -> str:
    if _looks_int(value):
        return "int"
    if _looks_float(value):
        return "float"
    if _looks_bool(value):
        return "bool"
    if _looks_datetime(value):
        return "datetime"
    if _looks_date(value):
        return "date"
    return "string"


def _looks_int(value: str) -> bool:
    if not value:
        return False
    try:
        int(value)
        return True
    except ValueError:
        return False


def _looks_float(value: str) -> bool:
    if not value:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def _looks_numeric(value: str) -> bool:
    return _looks_int(value) or _looks_float(value)


def _looks_bool(value: str) -> bool:
    v = value.strip().lower()
    return v in _BOOLEAN_TRUE or v in _BOOLEAN_FALSE


_DATE_LIKE = re.compile(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}")
_DATETIME_LIKE = re.compile(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}[ T]\d{1,2}:\d{2}")


def _looks_datetime(value: str) -> bool:
    if not _DATETIME_LIKE.match(value):
        return False
    for fmt in _DATE_FORMATS:
        if "%H" not in fmt:
            continue
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return False


def _looks_date(value: str) -> bool:
    if not _DATE_LIKE.match(value):
        return False
    for fmt in _DATE_FORMATS:
        if "%H" in fmt:
            continue
        try:
            datetime.strptime(value, fmt).date()
            return True
        except ValueError:
            continue
    return False
