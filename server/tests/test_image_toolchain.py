"""Tests for processors.kinds.meta_extract.toolchains.image."""

import io

import pytest
from PIL import Image

from domain.files.meta import FileMeta, build_file_meta
from processors.kinds.meta_extract.toolchains.image import (
    _parse_exif_datetime,
    _parse_gps_coord,
    empty_image_meta,
    parse,
    parse_image,
)


def _base_meta() -> dict:
    return build_file_meta(
        file_name="x.png",
        size=123,
        user_meta={},
        mimetype="image/png",
    )


def _rgb_png_bytes(*, size: tuple[int, int] = (32, 24), color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", size, color)
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_parse_png_dimensions_and_grayscale_color() -> None:
    content = _rgb_png_bytes(color=(200, 80, 80))
    meta = parse(content, existing_meta=_base_meta())

    assert meta["mimetype"] == "image/png"
    assert meta["kvs"]["width"] == 32
    assert meta["kvs"]["height"] == 24
    assert meta["tags"] == ["png", "small"]
    assert "png" in meta["keywords"]
    assert "rgb" in meta["keywords"]
    assert meta["summary"] == "small png image"


def test_parse_grayscale_rgb_equal_channels() -> None:
    content = _rgb_png_bytes(size=(10, 10), color=(50, 50, 50))
    meta = parse(content, existing_meta=_base_meta())
    assert "grayscale" in meta["tags"]


def test_parse_image_invalid_bytes_never_raises() -> None:
    meta = parse_image(content=b"not an image", existing_meta=_base_meta())
    assert meta == empty_image_meta(existing_meta=_base_meta())


def test_parse_image_empty_content() -> None:
    assert parse_image(content=b"", existing_meta=_base_meta()) == empty_image_meta(
        existing_meta=_base_meta()
    )


def test_image_meta_validates_parser_meta() -> None:
    content = _rgb_png_bytes(color=(1, 2, 3))
    image_meta = parse(content, existing_meta=_base_meta())
    FileMeta.model_validate(image_meta)


def test_rgba_png_has_alpha() -> None:
    buf = io.BytesIO()
    im = Image.new("RGBA", (4, 4), (255, 0, 0, 128))
    im.save(buf, format="PNG")
    meta = parse(buf.getvalue(), existing_meta=_base_meta())
    assert "transparent" in meta["tags"]


def test_parse_exif_datetime_iso() -> None:
    assert _parse_exif_datetime("2025:01:02 03:04:05") == "2025-01-02T03:04:05"
    assert _parse_exif_datetime("2025-01-02T03:04:05.12") == "2025-01-02T03:04:05"
    assert _parse_exif_datetime("") is None


def test_parse_gps_coord_signed() -> None:
    lat = _parse_gps_coord((37, 25, 30.0), "N")
    assert lat == pytest.approx(37.425)
    lon = _parse_gps_coord((122, 25, 30.0), "W")
    assert lon == pytest.approx(-122.425)
    assert _parse_gps_coord((200, 0, 0), "N") is None
    assert _parse_gps_coord((1, 2, 3), "X") is None
