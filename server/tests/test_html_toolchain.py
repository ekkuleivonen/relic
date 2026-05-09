"""Tests for parsers.toolchains.html."""

from file_meta import FileMeta, build_file_meta
from parsers.toolchains.html import empty_html_meta, parse, parse_html


def _base_meta(
    file_name: str = "page.html",
    mimetype: str = "text/html",
) -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype=mimetype,
    )


def _validate(meta: dict) -> None:
    FileMeta.model_validate(meta)


def test_parse_basic_metadata_visible_text_canonical_domain() -> None:
    raw = b"""<!DOCTYPE html>
<html lang="en">
<head>
<title>Brand Home</title>
<meta name="description" content="We build rockets and satellites."/>
<meta property="og:title" content="OG Welcome"/>
<meta property="og:description" content="Rocket company"/>
<meta property="og:type" content="website"/>
<link rel="canonical" href="https://example.org/pricing/tiers"/>
</head>
<body><h1>Lift off</h1><p>Houston standby readiness.</p>
<a href="https://partner.example/track">Partners</a>
<img src="/logo.png" alt=""/></body></html>
"""
    meta = parse(raw, existing_meta=_base_meta())

    assert meta["mimetype"] == "text/html"
    assert "html" in meta["tags"] and "webpage" in meta["tags"]
    assert "external-links" in meta["tags"]
    assert "has-images" in meta["tags"]
    assert "example.org" in meta["keywords"]
    assert meta["keywords"][:4] == [
        "example.org",
        "en",
        "brand home",
        "we build rockets and satellites.",
    ]
    assert "lift off" in meta["keywords"]
    assert meta["kvs"] == {
        "link_count": 1,
        "external_link_count": 1,
        "image_count": 1,
    }
    assert "HTML webpage" in meta["summary"]
    _validate(meta)


def test_parse_link_count_includes_internal_and_external() -> None:
    raw = (
        b"<!DOCTYPE html><html><body>"
        b'<a href="/docs">Docs</a>'
        b'<a href="#section">Skip</a>'
        b'<a href="https://other.example/p">Out</a>'
        b'<a href="">Empty</a>'
        b"</body></html>"
    )
    meta = parse(raw, existing_meta=_base_meta("links.html"))

    assert meta["kvs"]["link_count"] == 3
    assert meta["kvs"]["external_link_count"] == 1
    assert "external-links" in meta["tags"]
    _validate(meta)


def test_parse_article_semantics_from_element() -> None:
    raw = (
        "<!DOCTYPE html><html><body><article>"
        "<h2>About cats nap time</h2><p>Rest is productive.</p></article>"
        "</body></html>"
    ).encode()
    meta = parse(raw, existing_meta=_base_meta("cats.html"))

    assert "article" in meta["tags"]
    assert "about cats nap time" in meta["keywords"]
    assert meta["summary"].startswith("HTML article webpage")
    _validate(meta)


def test_parse_landing_page_from_json_ld_and_copy() -> None:
    chunks = "".join(f"<script>i={i}</script>" for i in range(12))
    raw = (
        f"<!DOCTYPE html><html><head><title>Pricing tiers</title></head>"
        f"<body>{chunks}<p>Select your pricing tier today.</p>"
        '<script type="application/ld+json">'
        '{"@type":"WebPage","url":"https://acme.test/"}'
        "</script>"
        "</body></html>"
    ).encode()
    meta = parse(raw, existing_meta=_base_meta("pricing.html"))

    assert "landing-page" in meta["tags"]
    assert "script-heavy" in meta["tags"]
    assert "pricing" in meta["keywords"]
    assert meta["kvs"]["script_count"] == 13
    _validate(meta)


def test_parse_html_never_raises() -> None:
    meta = parse_html(content=b"not html at all\x00\xff", existing_meta=_base_meta("x.html"))

    assert set(meta) == set(empty_html_meta(existing_meta=_base_meta()))
    FileMeta.model_validate(meta)
