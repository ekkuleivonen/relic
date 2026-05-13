"""Tests for processors.meta_extract.toolchains.archive."""

import io
import tarfile
import zipfile

from domain.files.meta import FileMeta, build_file_meta
from processors.meta_extract.toolchains.archive import empty_archive_meta, parse, parse_archive


def _base_meta(file_name: str = "bundle.zip", mimetype: str = "application/zip") -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype=mimetype,
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buf.getvalue()


def _tar_gz_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_parse_zip_source_code_single_folder() -> None:
    content = _zip_bytes(
        {
            "project/src/main.py": b"print('hi')",
            "project/pyproject.toml": b"[project]\nname='x'\n",
            "project/README.md": b"# Project\n",
        }
    )
    meta = parse(content, existing_meta=_base_meta("project.zip"))

    assert meta["tags"] == ["archive", "zip", "compressed", "bundle", "source-code", "single-folder"]
    assert meta["keywords"] == ["project", "py", "toml", "md", "src", "main", "pyproject", "readme"]
    assert meta["kvs"] == {"entry_count": 3, "uncompressed_size": 40}
    assert meta["summary"] == "zip archive containing source code"
    _validate_with_file(meta)


def test_parse_tar_gz_photos_many_files() -> None:
    content = _tar_gz_bytes(
        {
            f"photos/day1/img_{index}.jpg": b"jpeg"
            for index in range(12)
        }
    )
    meta = parse(content, existing_meta=_base_meta("photos.tar.gz", "application/gzip"))

    assert "tar" in meta["tags"]
    assert "compressed" in meta["tags"]
    assert "photos" in meta["tags"]
    assert "many-files" in meta["tags"]
    assert "photos" in meta["keywords"]
    assert "jpg" in meta["keywords"]
    assert meta["kvs"] == {"entry_count": 12, "uncompressed_size": 48}
    assert meta["summary"] == "tar.gz archive containing mostly images"
    _validate_with_file(meta)


def test_parse_documents_zip() -> None:
    content = _zip_bytes(
        {
            "docs/spec.pdf": b"pdf",
            "docs/notes.txt": b"notes",
            "docs/manual.docx": b"docx",
        }
    )
    meta = parse(content, existing_meta=_base_meta("docs.zip"))

    assert "documents" in meta["tags"]
    assert "pdf" in meta["keywords"]
    assert "txt" in meta["keywords"]
    assert "docx" in meta["keywords"]
    assert meta["summary"] == "zip archive containing documents"
    _validate_with_file(meta)


def test_parse_archive_never_raises_and_matches_parser_meta() -> None:
    meta = parse_archive(content=b"not an archive", existing_meta=_base_meta())

    assert meta == empty_archive_meta(existing_meta=_base_meta())
    _validate_with_file(meta)
