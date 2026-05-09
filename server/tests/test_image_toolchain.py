"""Tests for parsers.toolchains.image."""

import io

import pytest
from PIL import Image, ImageDraw

from file_meta import ParserMeta
from parsers.toolchains.image import (
    _parse_exif_datetime,
    _parse_gps_coord,
    empty_image_meta,
    parse,
    parse_image,
)


def _rgb_png_bytes(*, size: tuple[int, int] = (32, 24), color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", size, color)
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_parse_png_dimensions_and_grayscale_color() -> None:
    content = _rgb_png_bytes(color=(200, 80, 80))
    meta = parse(content)

    assert meta["width"] == 32
    assert meta["height"] == 24
    assert meta["format"] == "PNG"
    assert meta["color_mode"] == "RGB"
    assert meta["has_alpha"] is False
    assert meta["is_animated"] is False
    assert meta["is_grayscale"] is False
    assert meta["aspect_ratio"] == "4:3"
    assert meta["megapixels"] == pytest.approx(0.0)  # 32*24/1e6 rounds to 0.0
    assert meta["orientation"] is None


def test_parse_grayscale_rgb_equal_channels() -> None:
    content = _rgb_png_bytes(size=(10, 10), color=(50, 50, 50))
    meta = parse(content)
    assert meta["is_grayscale"] is True


def test_parse_image_invalid_bytes_never_raises() -> None:
    meta = parse_image(content=b"not an image")
    assert meta == empty_image_meta()


def test_parse_image_empty_content() -> None:
    assert parse_image(content=b"") == empty_image_meta()


def test_image_meta_validates_parser_meta() -> None:
    content = _rgb_png_bytes(color=(1, 2, 3))
    image_meta = parse(content)
    ParserMeta.model_validate(
        {
            "file": {
                "original_filename": "x.png",
                "size": 123,
                "mime_type": "image/png",
                "extension": "png",
            },
            "image": image_meta,
        }
    )


def test_rgba_png_has_alpha() -> None:
    buf = io.BytesIO()
    im = Image.new("RGBA", (4, 4), (255, 0, 0, 128))
    im.save(buf, format="PNG")
    meta = parse(buf.getvalue())
    assert meta["has_alpha"] is True


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
