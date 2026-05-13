"""Archive parser. Writes compact discovery metadata into file meta."""

from __future__ import annotations

import io
import re
import tarfile
import zipfile
from collections import Counter
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from file_meta import build_file_meta, build_parser_meta
from utils.logging import get_logger

log = get_logger(__name__)

_MAX_KEYWORDS = 50
_MANY_FILES_THRESHOLD = 10
_CODE_EXTENSIONS = {"go", "java", "js", "json", "py", "rs", "ts", "tsx"}
_CODE_FILENAMES = {"package.json", "pyproject.toml", "cargo.toml", "go.mod"}
_IMAGE_EXTENSIONS = {"avif", "gif", "heic", "jpeg", "jpg", "png", "webp"}
_DOCUMENT_EXTENSIONS = {"doc", "docx", "md", "odt", "pdf", "rtf", "txt"}


def empty_archive_meta(*, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shape matching parse() output for failed or unavailable archive parsing."""
    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=["archive"],
        keywords=[],
        kvs={},
    )


def parse_archive(
    *, content: bytes, existing_meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse archive bytes for storage in file meta. Never raises."""
    if not content:
        return empty_archive_meta(existing_meta=existing_meta)
    try:
        return parse(content, existing_meta=existing_meta)
    except (OSError, tarfile.TarError, zipfile.BadZipFile, ValueError) as exc:
        log.warning("archive_parse_failed", error=str(exc))
        return empty_archive_meta(existing_meta=existing_meta)
    except Exception as exc:
        log.warning("archive_parse_failed", error=str(exc))
        return empty_archive_meta(existing_meta=existing_meta)


def parse(content: bytes, *, existing_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse ZIP and TAR-family archives into the common discovery meta dict."""
    kind = _archive_kind(content=content, existing_meta=existing_meta)
    if kind == "zip":
        entries, encrypted = _zip_entries(content)
        details = _details(kind=kind, entries=entries, encrypted=encrypted)
    elif kind in {"tar", "tar.gz"}:
        entries = _tar_entries(content)
        details = _details(kind=kind, entries=entries, encrypted=False)
    else:
        raise ValueError("Unsupported archive")
    return _build_discovery_meta(details=details, existing_meta=existing_meta)


def _build_discovery_meta(
    *, details: dict[str, Any], existing_meta: dict[str, Any] | None
) -> dict[str, Any]:
    kind = details["kind"]
    bundle_tag = _bundle_tag(details["extension_counts"], details["names"])
    tags: list[str | None] = ["archive", kind.split(".")[0], "compressed", "bundle", bundle_tag]
    if details["encrypted"]:
        tags.append("encrypted")
    if details["single_folder"]:
        tags.append("single-folder")
    if details["entry_count"] >= _MANY_FILES_THRESHOLD:
        tags.append("many-files")

    keywords = _dedupe(
        [
            *details["top_folders"],
            *details["extension_counts"].keys(),
            *details["sample_names"],
        ],
        limit=_MAX_KEYWORDS,
    )

    base_meta = existing_meta or build_file_meta(file_name="", size=0, user_meta={})
    return build_parser_meta(
        existing=base_meta,
        tags=_dedupe(tags, limit=12),
        keywords=keywords,
        summary=_summary(kind=kind, bundle_tag=bundle_tag),
        kvs={
            "entry_count": details["entry_count"],
            "uncompressed_size": details["uncompressed_size"],
        },
    )


def _details(*, kind: str, entries: list[dict[str, Any]], encrypted: bool) -> dict[str, Any]:
    files = [entry for entry in entries if not entry["is_dir"]]
    names = [entry["name"] for entry in files]
    top_folders = _top_folders(names)
    extension_counts = _extension_counts(names)
    return {
        "kind": kind,
        "entry_count": len(files),
        "uncompressed_size": sum(entry["size"] for entry in files),
        "encrypted": encrypted,
        "names": names,
        "top_folders": top_folders,
        "extension_counts": extension_counts,
        "sample_names": _sample_names(names),
        "single_folder": len(top_folders) == 1,
    }


def _zip_entries(content: bytes) -> tuple[list[dict[str, Any]], bool]:
    entries: list[dict[str, Any]] = []
    encrypted = False
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for info in archive.infolist():
            encrypted = encrypted or bool(info.flag_bits & 0x1)
            entries.append(
                {
                    "name": info.filename,
                    "size": int(info.file_size),
                    "is_dir": info.is_dir(),
                }
            )
    return entries, encrypted


def _tar_entries(content: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
        for member in archive.getmembers():
            entries.append(
                {
                    "name": member.name,
                    "size": int(member.size) if member.isfile() else 0,
                    "is_dir": member.isdir(),
                }
            )
    return entries


def _archive_kind(*, content: bytes, existing_meta: dict[str, Any] | None) -> str | None:
    filename = _original_filename(existing_meta).lower()
    if content.startswith(b"PK\x03\x04") or filename.endswith(".zip"):
        return "zip"
    if filename.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    if filename.endswith(".tar"):
        return "tar"
    if content[257:262] == b"ustar":
        return "tar"
    return None


def _top_folders(names: list[str]) -> list[str]:
    folders: list[str] = []
    for name in names:
        parts = PurePosixPath(name).parts
        if len(parts) > 1:
            folders.append(parts[0])
    return _dedupe(folders, limit=10)


def _extension_counts(names: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for name in names:
        extension = PurePosixPath(name).suffix.removeprefix(".").lower()
        if extension:
            counts[extension] += 1
    return Counter(dict(counts.most_common(12)))


def _sample_names(names: list[str]) -> list[str]:
    samples: list[str] = []
    for name in names[:20]:
        path = PurePosixPath(name)
        samples.extend(part for part in path.parts[1:-1] if part)
        stem = path.stem
        samples.extend(
            word
            for word in re.split(r"[^A-Za-z0-9_+-]+", stem.lower())
            if len(word) >= 2 and not word.isdigit()
        )
    return _dedupe(samples, limit=20)


def _bundle_tag(extension_counts: Counter[str], names: list[str]) -> str | None:
    extensions = set(extension_counts)
    lower_names = {PurePosixPath(name).name.lower() for name in names}
    if extensions & _CODE_EXTENSIONS or lower_names & _CODE_FILENAMES:
        return "source-code"
    if _dominant(extensions=extensions, counts=extension_counts, candidates=_IMAGE_EXTENSIONS):
        return "photos"
    if _dominant(extensions=extensions, counts=extension_counts, candidates=_DOCUMENT_EXTENSIONS):
        return "documents"
    if any("backup" in word for name in names for word in PurePosixPath(name).parts):
        return "backup"
    return None


def _dominant(*, extensions: set[str], counts: Counter[str], candidates: set[str]) -> bool:
    matching = sum(count for ext, count in counts.items() if ext in candidates)
    total = sum(counts.values())
    return bool(extensions & candidates) and total > 0 and matching / total >= 0.6


def _summary(*, kind: str, bundle_tag: str | None) -> str:
    if bundle_tag == "source-code":
        return f"{kind} archive containing source code"
    if bundle_tag == "photos":
        return f"{kind} archive containing mostly images"
    if bundle_tag == "documents":
        return f"{kind} archive containing documents"
    if bundle_tag == "backup":
        return f"{kind} archive containing backup files"
    return f"{kind} archive bundle"


def _original_filename(existing_meta: dict[str, Any] | None) -> str:
    if not existing_meta:
        return ""
    return str(existing_meta.get("original_filename") or "")


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
