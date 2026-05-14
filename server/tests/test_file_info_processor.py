"""Smoke tests for FileInfoProcessor mimetype detection helpers.

Full integration coverage lives in ``test_processors_service.py`` — these
tests pin the pure helper logic that translates blob bytes + filename into
a mimetype/extension pair without touching S3 or the database.
"""

from processors.kinds.file_info import (
    detect_mime_type,
    detect_signature_mime_type,
)


def test_signature_detection_png() -> None:
    prefix = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    assert detect_signature_mime_type(prefix) == "image/png"


def test_signature_detection_jpeg() -> None:
    prefix = b"\xff\xd8\xff\xe0" + b"\x00" * 16
    assert detect_signature_mime_type(prefix) == "image/jpeg"


def test_signature_detection_pdf() -> None:
    assert detect_signature_mime_type(b"%PDF-1.4\n%abc\n") == "application/pdf"


def test_signature_detection_zip() -> None:
    assert detect_signature_mime_type(b"PK\x03\x04abc") == "application/zip"


def test_signature_detection_parquet() -> None:
    assert detect_signature_mime_type(b"PAR1abc") == "application/vnd.apache.parquet"


def test_signature_detection_html_handles_byte_order_mark() -> None:
    assert detect_signature_mime_type(b"\xef\xbb\xbf<!DOCTYPE html>") == "text/html"


def test_signature_detection_html_lowercase_html_tag() -> None:
    assert detect_signature_mime_type(b"<html><body></body></html>") == "text/html"


def test_signature_detection_unknown() -> None:
    assert detect_signature_mime_type(b"random gibberish prefix") is None


def test_detect_mime_type_falls_back_to_filename_for_parquet() -> None:
    assert detect_mime_type(prefix=b"", filename="data.parquet") == (
        "application/vnd.apache.parquet"
    )


def test_detect_mime_type_falls_back_to_html_extension() -> None:
    assert detect_mime_type(prefix=b"", filename="page.html") == "text/html"


def test_detect_mime_type_default_is_octet_stream() -> None:
    assert detect_mime_type(prefix=b"", filename="opaque.bin") == "application/octet-stream"


def test_detect_mime_type_signature_wins_over_filename() -> None:
    prefix = b"%PDF-1.7\n"
    assert detect_mime_type(prefix=prefix, filename="weird.txt") == "application/pdf"
