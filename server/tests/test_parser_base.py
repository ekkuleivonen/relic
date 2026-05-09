"""Tests for parser dispatch helpers."""

from parsers.base import detect_mime_type, is_parquet_file


def test_detect_mime_type_recognizes_parquet_extension_when_octet_stream() -> None:
    assert (
        detect_mime_type(prefix=b"", filename="part-00000-c000.snappy.parquet")
        == "application/vnd.apache.parquet"
    )


def test_is_parquet_file_accepts_generic_mime_with_parquet_extension() -> None:
    assert is_parquet_file(
        mime_type="application/octet-stream",
        parser_meta={"extension": "parquet"},
    )
