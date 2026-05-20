"""Tests for ingest-time blob mimetype/extension sniffing."""

from domain.blobs.sniff import detect_mime_type, detect_signature_mime_type, extension_from_filename


def test_detect_signature_mime_type_png() -> None:
    assert detect_signature_mime_type(b"\x89PNG\r\n\x1a\n\x00") == "image/png"


def test_detect_mime_type_prefers_signature_over_filename() -> None:
    assert (
        detect_mime_type(prefix=b"\x89PNG\r\n\x1a\n", filename="data.txt")
        == "image/png"
    )


def test_detect_mime_type_parquet_extension() -> None:
    assert (
        detect_mime_type(prefix=b"", filename="table.parquet")
        == "application/vnd.apache.parquet"
    )


def test_extension_from_filename() -> None:
    assert extension_from_filename("report.CSV") == "csv"
    assert extension_from_filename("noext") == ""
