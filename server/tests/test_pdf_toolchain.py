"""Tests for parsers.toolchains.pdf."""

import io

from pypdf import PdfWriter

from file_meta import FileMeta, build_file_meta
from parsers.toolchains.pdf import empty_pdf_meta, parse, parse_pdf


def _base_meta(file_name: str = "x.pdf") -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype="application/pdf",
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def _blank_pdf_bytes(*, metadata: dict[str, str] | None = None) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    if metadata:
        writer.add_metadata(metadata)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _encrypted_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("secret")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _text_pdf_bytes() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length 54 >>\nstream\nBT /F1 12 Tf 72 720 Td (Budget Report) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode())
        output.write(obj)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return output.getvalue()


def test_parse_metadata_and_page_count() -> None:
    content = _blank_pdf_bytes(
        metadata={
            "/Title": "Quarterly Report",
            "/Author": "Relic Team",
            "/Subject": "Budget",
        }
    )
    meta = parse(content, existing_meta=_base_meta())

    assert meta["tags"] == ["pdf", "document", "short"]
    assert meta["keywords"] == ["quarterly report", "relic team", "budget"]
    assert meta["kvs"]["page_count"] == 1
    assert meta["summary"] == "short PDF document"
    _validate_with_file(meta)


def test_parse_text_pdf_keywords_and_has_text() -> None:
    meta = parse(_text_pdf_bytes(), existing_meta=_base_meta("budget.pdf"))

    assert "has-text" in meta["tags"]
    assert "budget" in meta["keywords"]
    assert "report" in meta["keywords"]
    assert meta["kvs"]["page_count"] == 1
    _validate_with_file(meta)


def test_parse_encrypted_pdf_marks_protected() -> None:
    meta = parse(_encrypted_pdf_bytes(), existing_meta=_base_meta())

    assert "encrypted" in meta["tags"]
    assert meta["summary"] == "encrypted PDF document"
    _validate_with_file(meta)


def test_parse_pdf_never_raises_and_matches_parser_meta() -> None:
    meta = parse_pdf(content=b"not a pdf", existing_meta=_base_meta())

    assert meta == empty_pdf_meta(existing_meta=_base_meta())
    _validate_with_file(meta)
