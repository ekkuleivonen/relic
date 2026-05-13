"""Tests for processors.meta_extract.toolchains.office_doc."""

import io
import zipfile

from file_meta import FileMeta, build_file_meta
from processors.meta_extract.toolchains.office_doc import empty_office_doc_meta, parse, parse_office_doc


def _base_meta(
    file_name: str = "report.docx",
    mimetype: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
) -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype=mimetype,
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def _zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buf.getvalue()


def _docx_bytes() -> bytes:
    return _zip_bytes(
        {
            "[Content_Types].xml": (
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
            "docProps/core.xml": (
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:title>Quarterly Report</dc:title>"
                "<dc:creator>Relic Team</dc:creator>"
                "<dc:subject>Budget</dc:subject>"
                "</cp:coreProperties>"
            ),
            "docProps/app.xml": (
                '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                "<Pages>2</Pages><Words>6</Words>"
                "</Properties>"
            ),
            "word/document.xml": (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                "<w:body>"
                "<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>Executive Summary</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>This report covers budget planning.</w:t></w:r></w:p>"
                "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
                '<w:drawing r:embed="rId1"/>'
                "</w:body></w:document>"
            ),
            "word/comments.xml": (
                '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:comment><w:p><w:r><w:t>Needs review</w:t></w:r></w:p></w:comment>"
                "</w:comments>"
            ),
        }
    )


def _odt_bytes() -> bytes:
    return _zip_bytes(
        {
            "mimetype": "application/vnd.oasis.opendocument.text",
            "meta.xml": (
                '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0">'
                "<office:meta><dc:title>Contract Letter</dc:title><dc:creator>Ada</dc:creator>"
                "<meta:document-statistic meta:word-count=\"4\" meta:page-count=\"1\"/>"
                "</office:meta></office:document-meta>"
            ),
            "content.xml": (
                '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
                "<office:body><office:text>"
                '<text:h text:outline-level="1">Contract Terms</text:h>'
                "<text:p>Please sign this letter.</text:p>"
                "</office:text></office:body></office:document-content>"
            ),
        }
    )


def test_parse_docx_metadata_structure_and_keywords() -> None:
    meta = parse(_docx_bytes(), existing_meta=_base_meta())

    assert meta["tags"] == [
        "document",
        "word-document",
        "report",
        "has-images",
        "has-tables",
        "has-comments",
    ]
    assert meta["keywords"] == [
        "quarterly report",
        "relic team",
        "budget",
        "executive summary",
        "report",
    ]
    assert meta["kvs"] == {"word_count": 6, "page_count": 2}
    assert meta["summary"] == "word document report with tables, images, and comments"
    _validate_with_file(meta)


def test_parse_odt_metadata_and_type_terms() -> None:
    meta = parse(
        _odt_bytes(),
        existing_meta=_base_meta("contract.odt", "application/vnd.oasis.opendocument.text"),
    )

    assert meta["tags"] == ["document", "word-document", "letter", "contract"]
    assert "contract letter" in meta["keywords"]
    assert "contract terms" in meta["keywords"]
    assert meta["kvs"] == {"word_count": 4, "page_count": 1}
    assert meta["summary"] == "word document letter"
    _validate_with_file(meta)


def test_parse_rtf_basic_text() -> None:
    raw = br"{\rtf1\ansi\b Contract\par This contract is final.\par}"
    meta = parse(raw, existing_meta=_base_meta("contract.rtf", "application/rtf"))

    assert meta["tags"] == ["document", "word-document", "contract"]
    assert "contract" in meta["keywords"]
    assert meta["kvs"]["word_count"] == 5
    assert meta["summary"] == "word document contract"
    _validate_with_file(meta)


def test_parse_office_doc_never_raises_and_matches_parser_meta() -> None:
    meta = parse_office_doc(content=b"not office", existing_meta=_base_meta())

    assert meta == empty_office_doc_meta(existing_meta=_base_meta())
    _validate_with_file(meta)
