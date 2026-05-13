"""Tests for processors.meta_extract.toolchains.json."""

from file_meta import FileMeta, build_file_meta
from processors.meta_extract.toolchains.json import empty_json_meta, parse, parse_json


def _base_meta(file_name: str = "x.json") -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype="application/json",
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def test_parse_object_promotes_top_level_keys() -> None:
    meta = parse(b'{"name": "alice", "age": 30}', existing_meta=_base_meta())

    assert meta["tags"] == ["json", "data", "object"]
    assert meta["keywords"] == ["name", "age"]
    assert meta["summary"] == "JSON object with 2 top-level keys"
    assert meta["kvs"] == {}
    _validate_with_file(meta)


def test_parse_array_of_objects_as_records() -> None:
    raw = b'[{"email": "a@example.com", "created_at": "2026-01-01"}, {"email": "b@example.com"}]'
    meta = parse(raw, existing_meta=_base_meta())

    assert meta["tags"] == ["json", "data", "array", "records"]
    assert meta["kvs"]["record_count"] == 2
    assert meta["keywords"] == ["email", "created_at"]
    assert meta["summary"] == "JSON records with 2 rows and 2 fields"
    _validate_with_file(meta)


def test_parse_jsonl_records() -> None:
    raw = b'{"event": "login", "user_id": 1}\n{"event": "logout", "user_id": 1}\n'
    meta = parse(raw, existing_meta=_base_meta("events.jsonl"))

    assert meta["tags"] == ["json", "data", "jsonl", "records"]
    assert meta["kvs"]["record_count"] == 2
    assert meta["keywords"] == ["event", "user_id"]
    assert meta["summary"] == "JSONL records with 2 rows and 2 fields"
    _validate_with_file(meta)


def test_parse_known_schema_hints_from_filename_and_keys() -> None:
    raw = b'{"type": "FeatureCollection", "features": []}'
    meta = parse(raw, existing_meta=_base_meta("map.geojson"))

    assert "geo" in meta["tags"]
    assert "type" in meta["keywords"]
    assert "features" in meta["keywords"]
    assert "geo" in meta["keywords"]
    _validate_with_file(meta)


def test_parse_malformed_json_is_metadata_not_exception() -> None:
    meta = parse(b'{"broken": ', existing_meta=_base_meta())

    assert meta["tags"] == ["json", "data", "malformed"]
    assert meta["keywords"] == []
    assert meta["summary"] == "malformed JSON document"
    assert meta["kvs"] == {}
    _validate_with_file(meta)


def test_parse_json_never_raises_and_matches_parser_meta() -> None:
    meta = parse_json(content=b"\xff", existing_meta=_base_meta())

    assert set(meta) == set(empty_json_meta(existing_meta=_base_meta()))
    _validate_with_file(meta)
