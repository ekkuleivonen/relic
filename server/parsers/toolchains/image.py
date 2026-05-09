"""Image parser. Writes richer fields to parser_meta under the ``image`` key.

No configuration. Always extracts the same set of fields, with fallbacks
to capture data from quirky/non-standard image variants where possible.
"""

from __future__ import annotations

import io
import math
import re
from datetime import datetime
from typing import Any

import numpy as np
from PIL import ExifTags, Image, UnidentifiedImageError

from utils.logging import get_logger

log = get_logger(__name__)

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception as exc:
    log.warning("pillow_heif_unavailable", error=str(exc))

# Reverse map: tag name -> tag id, for both standard and EXIF IFD tags.
_TAG_NAME_TO_ID = {v: k for k, v in ExifTags.TAGS.items()}
_GPS_TAG_NAME_TO_ID = {v: k for k, v in ExifTags.GPSTAGS.items()}

# Pillow IFD identifiers (these are stable EXIF spec values, not Pillow constants).
_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825

# Sample for stat computation; we only need is_grayscale at this point so
# downscaling aggressively is fine.
_GRAYSCALE_SAMPLE_PIXELS = 100 * 100
_GRAYSCALE_RGB_DIFF_THRESHOLD = 5.0


def empty_image_meta() -> dict[str, Any]:
    """Same keys as parse(); all values None (for failed decode or empty input)."""
    return {
        "width": None,
        "height": None,
        "megapixels": None,
        "aspect_ratio": None,
        "format": None,
        "color_mode": None,
        "has_alpha": None,
        "is_animated": None,
        "is_grayscale": None,
        "orientation": None,
        "camera_make": None,
        "camera_model": None,
        "datetime_original": None,
        "gps_latitude": None,
        "gps_longitude": None,
    }


def parse_image(*, content: bytes) -> dict[str, Any]:
    """Parse image bytes for storage in parser_meta. Never raises."""
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
    """Parse image bytes into the catalog meta dict.

    Always returns the same set of keys; missing values are None.
    Never raises on missing or malformed metadata - only on undecodable images.
    """
    img = Image.open(io.BytesIO(content))

    result: dict[str, Any] = empty_image_meta()

    _extract_basic(img, result)
    _extract_exif(img, result)

    return result


# ---------------------------------------------------------------------------
# Basic shape
# ---------------------------------------------------------------------------


def _extract_basic(img: Image.Image, result: dict[str, Any]) -> None:
    w, h = img.size
    result["width"] = w
    result["height"] = h
    result["megapixels"] = round(w * h / 1_000_000, 2) if w and h else None
    result["aspect_ratio"] = _aspect_ratio(w, h)

    result["format"] = img.format
    result["color_mode"] = img.mode
    result["has_alpha"] = _has_alpha(img)
    result["is_animated"] = bool(getattr(img, "is_animated", False))
    result["is_grayscale"] = _is_grayscale(img)


def _aspect_ratio(w: int, h: int) -> str | None:
    if not w or not h:
        return None
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


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

    # Orientation lives on the main IFD.
    result["orientation"] = _get_int(exif, "Orientation")

    # Camera make/model: try main IFD first, then the EXIF sub-IFD as fallback.
    # Some software writes these in unexpected places.
    exif_ifd = _safe_ifd(exif, _EXIF_IFD)

    result["camera_make"] = _get_str(exif, "Make") or _get_str(exif_ifd, "Make")
    result["camera_model"] = _get_str(exif, "Model") or _get_str(exif_ifd, "Model")

    # DateTimeOriginal is in the EXIF sub-IFD; fall back to DateTimeDigitized
    # and finally to the main IFD's DateTime (modification time, less ideal
    # but better than nothing).
    dt_raw = (
        _get_str(exif_ifd, "DateTimeOriginal")
        or _get_str(exif_ifd, "DateTimeDigitized")
        or _get_str(exif, "DateTime")
    )
    result["datetime_original"] = _parse_exif_datetime(dt_raw)

    # GPS lives on its own IFD. Some images have GPS data that doesn't decode
    # via get_ifd; try both paths.
    gps_ifd = _safe_ifd(exif, _GPS_IFD)
    if gps_ifd:
        result["gps_latitude"] = _parse_gps_coord(
            gps_ifd.get(_GPS_TAG_NAME_TO_ID.get("GPSLatitude")),
            gps_ifd.get(_GPS_TAG_NAME_TO_ID.get("GPSLatitudeRef")),
        )
        result["gps_longitude"] = _parse_gps_coord(
            gps_ifd.get(_GPS_TAG_NAME_TO_ID.get("GPSLongitude")),
            gps_ifd.get(_GPS_TAG_NAME_TO_ID.get("GPSLongitudeRef")),
        )


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


def _get_int(ifd: Any, tag_name: str) -> int | None:
    if not ifd:
        return None
    tag_id = _TAG_NAME_TO_ID.get(tag_name)
    if tag_id is None:
        return None
    val = ifd.get(tag_id)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


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
