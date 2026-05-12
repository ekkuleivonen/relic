"""Tests for canonical File.meta helpers."""

from file_meta import build_file_meta, merge_parser_meta, validate_file_meta_dict


def test_merge_parser_meta_upgrades_unknown_mimetype() -> None:
    existing = build_file_meta(
        file_name="part-00000-c000.snappy.parquet",
        size=10,
        user_meta={},
        mimetype="application/octet-stream",
    )
    parsed = build_file_meta(
        file_name="part-00000-c000.snappy.parquet",
        size=10,
        user_meta={},
        mimetype="application/vnd.apache.parquet",
    )

    merged = merge_parser_meta(existing=existing, parsed=parsed)

    assert merged["mimetype"] == "application/vnd.apache.parquet"


def test_merge_parser_meta_preserves_specific_mimetype() -> None:
    existing = build_file_meta(
        file_name="photo.jpeg",
        size=10,
        user_meta={},
        mimetype="image/jpeg",
    )
    parsed = build_file_meta(
        file_name="photo.jpeg",
        size=10,
        user_meta={},
        mimetype="application/octet-stream",
    )

    merged = merge_parser_meta(existing=existing, parsed=parsed)

    assert merged["mimetype"] == "image/jpeg"


def test_missing_summary_normalizes_for_existing_persisted_meta() -> None:
    existing = build_file_meta(
        file_name="legacy.csv",
        size=10,
        user_meta={},
        mimetype="text/csv",
    )
    existing.pop("summary")

    normalized = validate_file_meta_dict(existing).model_dump(mode="json")

    assert normalized["summary"] is None
