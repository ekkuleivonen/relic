"""Image parser.

Extracts deterministic image facts and reduces them to the common parser
discovery shape: ``tags``, ``keywords``, ``summary``, and compact ``kvs``.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

import numpy as np
from PIL import ExifTags, Image, UnidentifiedImageError

from domain.files.meta import build_parser_discovery, empty_parser_discovery
from utils.logging import get_logger

log = get_logger(__name__)

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception as exc:
    log.warning("pillow_heif_unavailable", error=str(exc))

# Reverse map: tag name -> tag id, for both standard and EXIF IFD tags.
_TAG_NAME_TO_ID = {v: k for k, v in ExifTags.TAGS.items()}

# Pillow IFD identifiers (these are stable EXIF spec values, not Pillow constants).
_EXIF_IFD = 0x8769

# Sample for stat computation; we only need is_grayscale at this point so
# downscaling aggressively is fine.
_GRAYSCALE_SAMPLE_PIXELS = 100 * 100
_GRAYSCALE_RGB_DIFF_THRESHOLD = 5.0


def empty_image_meta() -> dict[str, Any]:
    """Shape matching parse() output for failed or unavailable image parsing."""
    return empty_parser_discovery(tags=["image"])


def parse_image(*, content: bytes) -> dict[str, Any]:
    """Parse image bytes into a discovery payload. Never raises."""
    if not content:
        return empty_image_meta()
    try:
        return parse(content)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        log.warning("image_decode_failed", error=str(exc))
        return empty_image_meta()
    except Exception as exc:  # pillow / codec edge cases
        log.warning("image_parse_failed", error=str(exc))
        return empty_image_meta()


def parse(content: bytes) -> dict[str, Any]:
    """Parse image bytes into the common discovery payload.

    Never raises on missing or malformed metadata - only on undecodable images.
    """
    img = Image.open(io.BytesIO(content))

    details: dict[str, Any] = {}

    _extract_basic(img, details)
    _extract_exif(img, details)

    return _build_discovery(details)


# ---------------------------------------------------------------------------
# Basic shape
# ---------------------------------------------------------------------------


def _extract_basic(img: Image.Image, result: dict[str, Any]) -> None:
    w, h = img.size
    result["width"] = w
    result["height"] = h

    result["format"] = img.format
    result["color_mode"] = img.mode
    result["has_alpha"] = _has_alpha(img)
    result["is_animated"] = bool(getattr(img, "is_animated", False))
    result["is_grayscale"] = _is_grayscale(img)


def _build_discovery(details: dict[str, Any]) -> dict[str, Any]:
    width = details.get("width")
    height = details.get("height")
    image_format = _normalize_token(details.get("format"))
    color_mode = _normalize_token(details.get("color_mode"))

    tags = ["image"]
    if image_format:
        tags.append(image_format)
    if details.get("is_animated"):
        tags.append("animated")
    if details.get("has_alpha"):
        tags.append("transparent")
    if details.get("is_grayscale"):
        tags.append("grayscale")
    size_tag = _image_size_tag(width, height)
    if size_tag:
        tags.append(size_tag)

    keywords = _dedupe(
        [
            image_format,
            color_mode,
            _normalize_keyword(details.get("camera_make")),
            _normalize_keyword(details.get("camera_model")),
        ]
    )

    kvs: dict[str, Any] = {}
    if width is not None:
        kvs["width"] = width
    if height is not None:
        kvs["height"] = height

    summary_parts = [
        tag
        for tag in [
            size_tag,
            "animated" if details.get("is_animated") else None,
            "transparent" if details.get("has_alpha") else None,
            "grayscale" if details.get("is_grayscale") else None,
            image_format,
        ]
        if tag
    ]
    summary = " ".join([*summary_parts, "image"]).strip() or "image"

    return build_parser_discovery(
        tags=[tag for tag in _dedupe(tags) if tag != "image"],
        keywords=keywords,
        summary=summary,
        kvs=kvs,
    )


def _image_size_tag(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    pixels = width * height
    if pixels < 512 * 512:
        return "small"
    if pixels >= 4_000_000:
        return "large"
    return None


def _normalize_token(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower()
    return token or None


def _normalize_keyword(value: Any) -> str | None:
    if value is None:
        return None
    keyword = re.sub(r"\s+", " ", str(value).strip().lower())
    return keyword or None


def _dedupe(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

def _has_alpha(img: Image.Image) -> bool:
    # The mode-based check covers most cases; the band check catches modes
    # like "P" with a transparency entry.
    if img.mode in ("RGBA", "LA", "PA", "RGBa", "La"):
        return True
    if "A" in img.getbands():
        return True
    if "transparency" in img.info:
        return True
    return False


def _is_grayscale(img: Image.Image) -> bool:
    # Mode-based shortcut for the easy cases.
    if img.mode in ("1", "L", "LA", "I", "F"):
        return True
    if img.mode not in ("RGB", "RGBA", "P"):
        # Unknown territory; assume color.
        return False

    # Sample to avoid loading huge images. RGB conversion handles palette
    # ("P") and alpha modes uniformly.
    rgb = img.convert("RGB")
    w, h = rgb.size
    if w * h > _GRAYSCALE_SAMPLE_PIXELS:
        scale = (_GRAYSCALE_SAMPLE_PIXELS / (w * h)) ** 0.5
        rgb = rgb.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.LANCZOS,
        )

    arr = np.asarray(rgb, dtype=np.int16)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    avg_diff = float(np.mean(np.abs(r - g)) + np.mean(np.abs(g - b)))
    return avg_diff < _GRAYSCALE_RGB_DIFF_THRESHOLD


# ---------------------------------------------------------------------------
# EXIF
# ---------------------------------------------------------------------------


def _extract_exif(img: Image.Image, result: dict[str, Any]) -> None:
    exif = img.getexif()
    if not exif:
        return

    # Camera make/model: try main IFD first, then the EXIF sub-IFD as fallback.
    # Some software writes these in unexpected places.
    exif_ifd = _safe_ifd(exif, _EXIF_IFD)

    result["camera_make"] = _get_str(exif, "Make") or _get_str(exif_ifd, "Make")
    result["camera_model"] = _get_str(exif, "Model") or _get_str(exif_ifd, "Model")


def _safe_ifd(exif: Any, ifd_id: int) -> Any:
    """get_ifd raises on malformed EXIF; swallow and return empty dict."""
    if exif is None:
        return {}
    try:
        return exif.get_ifd(ifd_id) or {}
    except Exception:
        return {}


def _get_str(ifd: Any, tag_name: str) -> str | None:
    if not ifd:
        return None
    tag_id = _TAG_NAME_TO_ID.get(tag_name)
    if tag_id is None:
        return None
    val = ifd.get(tag_id)
    if val is None:
        return None
    if isinstance(val, bytes):
        try:
            val = val.decode("utf-8", errors="replace")
        except Exception:
            return None
    s = str(val).strip().strip("\x00")
    return s or None


def _parse_exif_datetime(raw: str | None) -> str | None:
    """Parse EXIF DateTime ('YYYY:MM:DD HH:MM:SS') into ISO 8601.

    Returns None if the value can't be parsed. Tolerates trailing subsecond
    junk and unusual separators.
    """
    if not raw:
        return None
    # Common case: "2025:11:14 14:32:11"
    m = re.match(
        r"^\s*(\d{4})[:\-/](\d{1,2})[:\-/](\d{1,2})[ T](\d{1,2}):(\d{1,2}):(\d{1,2})",
        raw,
    )
    if not m:
        return None
    try:
        dt = datetime(
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            int(m.group(4)),
            int(m.group(5)),
            int(m.group(6)),
        )
    except ValueError:
        return None
    return dt.isoformat()


def _parse_gps_coord(coord: Any, ref: Any) -> float | None:
    """Convert EXIF GPS rationals + ref direction into signed decimal degrees."""
    if not coord or not ref:
        return None
    try:
        # Accept tuples of (deg, min, sec) where each can be a Rational or float
        deg = float(coord[0])
        minutes = float(coord[1])
        seconds = float(coord[2])
    except (TypeError, IndexError, ValueError, ZeroDivisionError):
        return None

    decimal = deg + minutes / 60 + seconds / 3600

    if isinstance(ref, bytes):
        try:
            ref = ref.decode("ascii", errors="replace")
        except Exception:
            return None
    ref_str = str(ref).strip().upper()

    if ref_str in ("S", "W"):
        decimal = -decimal
    elif ref_str not in ("N", "E"):
        # Unknown reference - don't trust the sign.
        return None

    # Sanity-check: latitudes must be in [-90, 90], longitudes in [-180, 180].
    # The caller doesn't tell us which we're parsing, so use the wider range.
    if not -180.0 <= decimal <= 180.0:
        return None

    return round(decimal, 6)
