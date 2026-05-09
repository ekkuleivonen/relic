"""Tests for parsers.toolchains.csv."""

from file_meta import ParserMeta
from parsers.toolchains.csv import empty_csv_meta, parse, parse_csv


def _validate_with_file(csv_meta: dict) -> None:
    ParserMeta.model_validate(
        {
            "file": {
                "original_filename": "x.csv",
                "size": 10,
                "mime_type": "text/csv",
                "extension": "csv",
            },
            "csv": csv_meta,
        }
    )


def test_parse_simple_comma_header() -> None:
    raw = b"name,age\nalice,30\nbob,31\n"
    meta = parse(raw)
    assert meta["row_count"] == 2
    assert meta["column_count"] == 2
    assert meta["columns"] == ["name", "age"]
    assert meta["column_types"]["name"] == "string"
    assert meta["column_types"]["age"] == "int"
    assert meta["delimiter"] == ","
    assert meta["encoding"] == "utf-8"
    assert meta["empty_cells_pct"] == 0.0
    _validate_with_file(meta)


def test_parse_semicolon_no_header_numeric_cols() -> None:
    raw = b"1;2\n3;4\n"
    meta = parse(raw)
    assert meta["row_count"] == 2
    assert meta["column_count"] == 2
    assert meta["delimiter"] == ";"
    _validate_with_file(meta)


def test_parse_empty_file() -> None:
    meta = parse(b"")
    assert meta["row_count"] == 0
    assert meta["column_count"] == 0
    assert meta["columns"] == []
    assert meta["column_types"] == {}
    assert meta["empty_cells_pct"] == 0.0
    _validate_with_file(meta)


def test_parse_skip_preamble_comment_rows() -> None:
    raw = b"# export v1\n\nSummary: foo\na,b\n1,2\n3,4\n"
    meta = parse(raw)
    assert meta["skipped_prefix_rows"] >= 1
    assert meta["row_count"] == 2
    assert "a" in meta["columns"] or "col_1" in meta["columns"]
    _validate_with_file(meta)


def test_parse_csv_never_raises_and_matches_parser_meta() -> None:
    meta = parse_csv(content=b"\x00\xff\xff broken")
    assert set(meta) == set(empty_csv_meta())
    _validate_with_file(meta)


def test_type_inference_mixed_column() -> None:
    raw = b"x\n1\ny\n"
    meta = parse(raw)
    col_name = meta["columns"][0]
    assert meta["column_types"][col_name] == "mixed"


def test_normalize_header_duplicate_columns() -> None:
    raw = b"a,a\n1,2\n"
    meta = parse(raw)
    assert meta["columns"] == ["a", "a_2"]
