"""Tests for the sectioned ``File.meta`` shape.

Each processor kind owns ``meta.sections.<kind>``; the top-level fields are a
derived merged view recomputed by ``apply_section``. These tests pin that
contract so processors / search / UI all see consistent reads.
"""

import datetime as dt

import pytest

from domain.files.meta import (
    FileMetaSection,
    apply_section,
    build_parser_discovery,
    build_section_payload,
    empty_parser_discovery,
    init_file_meta,
    mark_section,
    validate_file_meta_dict,
)


def _base_meta() -> dict:
    return init_file_meta(
        file_name="report.csv",
        size=128,
        user_meta={"tags": ["external"], "kvs": {"owner": "research"}},
        mimetype="text/csv",
    )


def test_init_file_meta_seeds_user_only_top_level() -> None:
    meta = _base_meta()

    assert meta["size"] == 128
    assert meta["mimetype"] == "text/csv"
    assert meta["extension"] == "csv"
    assert meta["original_filename"] == "report.csv"
    assert meta["user_tags"] == ["external"]
    assert meta["user_kvs"] == {"owner": "research"}
    assert meta["sections"] == {}
    assert meta["tags"] == ["external"]
    assert meta["kvs"] == {"owner": "research"}
    assert meta["summary"] is None


def test_apply_section_merges_section_into_top_level() -> None:
    meta = _base_meta()

    section = build_section_payload(
        status="completed",
        extracted_at=dt.datetime(2026, 5, 14, tzinfo=dt.UTC),
        tags=["data", "csv"],
        keywords=["sales", "Q1"],
        summary="data csv",
        kvs={"row_count": 12, "delimiter": ","},
    )
    updated = apply_section(meta, kind="csv_meta", section=section)

    assert "csv_meta" in updated["sections"]
    assert updated["sections"]["csv_meta"]["tags"] == ["data", "csv"]
    assert "data" in updated["tags"] and "csv" in updated["tags"]
    assert "external" in updated["tags"]
    assert "sales" in updated["keywords"]
    assert updated["summary"] == "data csv"
    assert updated["kvs"]["csv_meta.row_count"] == 12
    assert updated["kvs"]["owner"] == "research"


def test_apply_section_file_info_overrides_top_level() -> None:
    meta = _base_meta()
    meta["mimetype"] = "application/octet-stream"

    section = build_section_payload(
        status="completed",
        extracted_at=dt.datetime(2026, 5, 14, tzinfo=dt.UTC),
        tags=["text"],
        summary="text/csv (128 bytes)",
        kvs={"size": 128, "extension": "csv", "mimetype": "text/csv"},
    )
    updated = apply_section(
        meta,
        kind="file_info",
        section=section,
        base_overrides={"mimetype": "text/csv", "extension": "csv", "size": 128},
    )

    assert updated["mimetype"] == "text/csv"
    assert updated["extension"] == "csv"
    assert updated["summary"] == "text/csv (128 bytes)"


def test_apply_section_failed_section_does_not_pollute_top_level() -> None:
    meta = _base_meta()
    failed = build_section_payload(
        status="failed",
        extracted_at=dt.datetime(2026, 5, 14, tzinfo=dt.UTC),
        tags=["should-not-leak"],
        keywords=["nope"],
        error_class="ValueError",
        error_message="boom",
    )
    updated = apply_section(meta, kind="image_meta", section=failed)

    assert updated["sections"]["image_meta"]["status"] == "failed"
    assert "should-not-leak" not in updated["tags"]


def test_mark_section_updates_only_status() -> None:
    meta = _base_meta()
    completed = build_section_payload(
        status="completed",
        extracted_at=dt.datetime(2026, 5, 14, tzinfo=dt.UTC),
        tags=["existing"],
    )
    meta = apply_section(meta, kind="csv_meta", section=completed)

    marked = mark_section(
        meta,
        kind="csv_meta",
        status="failed",
        error_class="OSError",
        error_message="transient",
    )

    assert marked["sections"]["csv_meta"]["status"] == "failed"
    assert marked["sections"]["csv_meta"]["error_class"] == "OSError"
    # Failed sections drop out of the merged view.
    assert "existing" not in marked["tags"]


def test_validate_file_meta_dict_round_trips() -> None:
    meta = _base_meta()
    parsed = validate_file_meta_dict(meta)
    assert parsed.size == 128
    assert parsed.sections == {}


def test_apply_section_rejects_unknown_base_override() -> None:
    meta = _base_meta()
    with pytest.raises(ValueError):
        apply_section(
            meta,
            kind="file_info",
            section=FileMetaSection(),
            base_overrides={"summary": "boom"},
        )


def test_build_parser_discovery_normalizes_tags_and_kvs() -> None:
    payload = build_parser_discovery(
        tags=["one", "two", "two"],
        keywords="alpha, beta",
        summary=" trimmed ",
        kvs={"count": 2},
    )

    assert payload["tags"] == ["one", "two"]
    assert payload["keywords"] == ["alpha", "beta"]
    assert payload["summary"] == "trimmed"
    assert payload["kvs"] == {"count": 2}


def test_empty_parser_discovery_with_defaults() -> None:
    payload = empty_parser_discovery(tags=["fallback"], summary="empty")
    assert payload == {
        "tags": ["fallback"],
        "keywords": [],
        "summary": "empty",
        "kvs": {},
    }
