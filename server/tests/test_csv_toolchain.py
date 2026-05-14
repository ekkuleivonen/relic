"""Tests for processors.kinds.meta_extract.toolchains.csv."""

from domain.files.meta import FileMeta, build_file_meta
from processors.kinds.meta_extract.toolchains.csv import empty_csv_meta, parse, parse_csv


def _base_meta() -> dict:
    return build_file_meta(
        file_name="x.csv",
        size=10,
        user_meta={},
        mimetype="text/csv",
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def test_parse_simple_comma_header() -> None:
    raw = b"name,age\nalice,30\nbob,31\n"
    meta = parse(raw, existing_meta=_base_meta())
    assert meta["mimetype"] == "text/csv"
    assert meta["kvs"]["row_count"] == 2
    assert meta["kvs"]["column_count"] == 2
    assert meta["tags"] == ["data", "table"]
    assert meta["keywords"] == ["name", "age", "string", "int"]
    assert meta["summary"] == "CSV table with 2 rows and 2 columns"
    _validate_with_file(meta)


def test_parse_semicolon_no_header_numeric_cols() -> None:
    raw = b"1;2\n3;4\n"
    meta = parse(raw, existing_meta=_base_meta())
    assert meta["kvs"]["row_count"] == 2
    assert meta["kvs"]["column_count"] == 2
    assert "table" in meta["tags"]
    _validate_with_file(meta)


def test_parse_empty_file() -> None:
    meta = parse(b"", existing_meta=_base_meta())
    assert meta["tags"] == ["data", "empty"]
    assert meta["keywords"] == []
    assert meta["kvs"]["row_count"] == 0
    assert meta["kvs"]["column_count"] == 0
    _validate_with_file(meta)


def test_parse_skip_preamble_comment_rows() -> None:
    raw = b"# export v1\n\nSummary: foo\na,b\n1,2\n3,4\n"
    meta = parse(raw, existing_meta=_base_meta())
    assert meta["kvs"]["row_count"] == 2
    assert meta["kvs"]["column_count"] == 2
    assert "a" in meta["keywords"] or "col_1" in meta["keywords"]
    _validate_with_file(meta)


def test_parse_csv_never_raises_and_matches_parser_meta() -> None:
    meta = parse_csv(content=b"\x00\xff\xff broken", existing_meta=_base_meta())
    assert set(meta) == set(empty_csv_meta(existing_meta=_base_meta()))
    _validate_with_file(meta)


def test_type_inference_mixed_column() -> None:
    raw = b"x\n1\ny\n"
    meta = parse(raw, existing_meta=_base_meta())
    assert "mixed" in meta["keywords"]


def test_normalize_header_duplicate_columns() -> None:
    raw = b"a,a\n1,2\n"
    meta = parse(raw, existing_meta=_base_meta())
    assert "a" in meta["keywords"]
    assert "a_2" in meta["keywords"]


def test_generated_column_names_are_not_keywords() -> None:
    raw = b"1,2\n3,4\n"
    meta = parse(raw, existing_meta=_base_meta())
    assert "col_1" not in meta["keywords"]
    assert "col_2" not in meta["keywords"]
