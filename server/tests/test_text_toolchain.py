"""Tests for processors.meta_extract.toolchains.text."""

from domain.files.meta import FileMeta, build_file_meta
from processors.meta_extract.toolchains.text import empty_text_meta, parse, parse_text


def _base_meta(file_name: str = "notes.txt", mimetype: str = "text/plain") -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype=mimetype,
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def test_parse_plain_text_note_with_heading() -> None:
    raw = b"# Project Notes\n\nRemember to review parser output.\nParser output should stay compact.\n"
    meta = parse(raw, existing_meta=_base_meta())

    assert meta["tags"] == ["text", "plain-text", "notes", "short"]
    assert "project" in meta["keywords"]
    assert "notes" in meta["keywords"]
    assert "parser" in meta["keywords"]
    assert meta["kvs"]["line_count"] == 4
    assert meta["kvs"]["word_count"] == 12
    assert meta["summary"] == "short plain text note"
    _validate_with_file(meta)


def test_parse_log_from_filename_and_log_markers() -> None:
    raw = b"2026-05-10 01:02:03 INFO started\n2026-05-10 01:02:04 ERROR failed\n"
    meta = parse(raw, existing_meta=_base_meta("app.log"))

    assert "log" in meta["tags"]
    assert "app" in meta["keywords"]
    assert "error" in meta["keywords"]
    assert meta["summary"] == "short log-like text file"
    _validate_with_file(meta)


def test_parse_config_key_value_labels() -> None:
    raw = b"database_url=postgres://example\nredis_host=localhost\n"
    meta = parse(raw, existing_meta=_base_meta("settings.env"))

    assert "config" in meta["tags"]
    assert "database_url" in meta["keywords"]
    assert "redis_host" in meta["keywords"]
    assert meta["summary"] == "short config-like text file"
    _validate_with_file(meta)


def test_parse_license_marker() -> None:
    raw = b"MIT License\n\nPermission is hereby granted, free of charge...\n"
    meta = parse(raw, existing_meta=_base_meta("LICENSE"))

    assert "license" in meta["tags"]
    assert "mit" in meta["keywords"]
    assert "license" in meta["keywords"]
    assert meta["summary"] == "short license text file"
    _validate_with_file(meta)


def test_parse_empty_text() -> None:
    meta = parse(b"", existing_meta=_base_meta())

    assert meta["tags"] == ["text", "plain-text", "empty"]
    assert meta["keywords"] == ["notes", "txt"]
    assert meta["kvs"] == {"line_count": 0, "word_count": 0}
    assert meta["summary"] == "empty plain text file"
    _validate_with_file(meta)


def test_parse_text_never_raises_and_matches_parser_meta() -> None:
    meta = parse_text(content=b"\x00\x01\x02\x03", existing_meta=_base_meta("x.bin"))

    assert meta == empty_text_meta(existing_meta=_base_meta("x.bin"))
    _validate_with_file(meta)
