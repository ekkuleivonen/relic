"""Tests for processors.meta_extract.toolchains.video."""

import struct

from file_meta import FileMeta, build_file_meta
from processors.meta_extract.toolchains.video import empty_video_meta, parse, parse_video


def _base_meta(file_name: str = "video.mp4", mimetype: str = "video/mp4") -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype=mimetype,
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def _full_box(kind: bytes, payload: bytes, *, flags: int = 0) -> bytes:
    return _box(kind, bytes([0, (flags >> 16) & 0xFF, (flags >> 8) & 0xFF, flags & 0xFF]) + payload)


def _mvhd(*, timescale: int = 1000, duration: int = 12_000) -> bytes:
    payload = (
        struct.pack(">IIII", 0, 0, timescale, duration)
        + b"\x00" * 80
    )
    return _full_box(b"mvhd", payload)


def _tkhd(*, width: int, height: int) -> bytes:
    payload = (
        struct.pack(">IIIII", 0, 0, 1, 0, 0)
        + b"\x00" * 8
        + b"\x00" * 8
        + b"\x00" * 36
        + struct.pack(">II", width << 16, height << 16)
    )
    return _full_box(b"tkhd", payload, flags=0x000007)


def _hdlr(handler: bytes) -> bytes:
    payload = b"\x00" * 4 + handler + b"\x00" * 12 + handler + b"\x00"
    return _full_box(b"hdlr", payload)


def _trak(*, handler: bytes, width: int = 1920, height: int = 1080) -> bytes:
    return _box(b"trak", _tkhd(width=width, height=height) + _box(b"mdia", _hdlr(handler)))


def _mp4_bytes(
    *,
    major_brand: bytes = b"isom",
    width: int = 1920,
    height: int = 1080,
    duration_ms: int = 12_000,
    has_audio: bool = True,
) -> bytes:
    ftyp = _box(b"ftyp", major_brand + b"\x00\x00\x02\x00" + b"isommp42")
    tracks = [_trak(handler=b"vide", width=width, height=height)]
    if has_audio:
        tracks.append(_trak(handler=b"soun", width=0, height=0))
    moov = _box(b"moov", _mvhd(duration=duration_ms) + b"".join(tracks))
    return ftyp + moov


def _riff_chunk(kind: bytes, payload: bytes) -> bytes:
    padding = b"\x00" if len(payload) % 2 else b""
    return kind + struct.pack("<I", len(payload)) + payload + padding


def _riff_list(kind: bytes, payload: bytes) -> bytes:
    return _riff_chunk(b"LIST", kind + payload)


def _avi_stream_header(kind: bytes, handler: bytes) -> bytes:
    return _riff_chunk(b"strh", kind + handler + b"\x00" * 48)


def _avi_bytes(
    *,
    width: int = 1280,
    height: int = 720,
    total_frames: int = 300,
    microseconds_per_frame: int = 40_000,
    has_audio: bool = True,
) -> bytes:
    avih = _riff_chunk(
        b"avih",
        struct.pack(
            "<IIIIIIIIII",
            microseconds_per_frame,
            0,
            0,
            0,
            total_frames,
            0,
            2 if has_audio else 1,
            0,
            width,
            height,
        )
        + b"\x00" * 16,
    )
    streams = [
        _riff_list(b"strl", _avi_stream_header(b"vids", b"MJPG")),
    ]
    if has_audio:
        streams.append(_riff_list(b"strl", _avi_stream_header(b"auds", b"\x01\x00\x00\x00")))
    hdrl = _riff_list(b"hdrl", avih + b"".join(streams))
    riff_payload = b"AVI " + hdrl
    return b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload


def test_parse_mp4_duration_dimensions_and_audio() -> None:
    meta = parse(_mp4_bytes(), existing_meta=_base_meta())

    assert meta["tags"] == ["video", "mp4", "has-audio", "short", "hd"]
    assert meta["keywords"] == ["video", "mp4"]
    assert meta["kvs"] == {
        "duration_seconds": 12.0,
        "width": 1920,
        "height": 1080,
    }
    assert meta["summary"] == "short 1080p mp4 video with audio"
    _validate_with_file(meta)


def test_parse_avi_duration_dimensions_audio_and_codec() -> None:
    meta = parse(_avi_bytes(), existing_meta=_base_meta("camera.avi", "video/x-msvideo"))

    assert meta["tags"] == ["video", "avi", "has-audio", "short", "hd"]
    assert meta["keywords"] == ["camera", "avi", "mjpg"]
    assert meta["kvs"] == {
        "duration_seconds": 12.0,
        "width": 1280,
        "height": 720,
    }
    assert meta["summary"] == "short 720p avi video with audio"
    _validate_with_file(meta)


def test_parse_vertical_phone_video_from_filename() -> None:
    meta = parse(
        _mp4_bytes(major_brand=b"qt  ", width=1080, height=1920, has_audio=False),
        existing_meta=_base_meta("IMG_1234.MOV", "video/quicktime"),
    )

    assert "phone-video" in meta["tags"]
    assert "silent" in meta["tags"]
    assert "vertical" in meta["tags"]
    assert meta["kvs"]["width"] == 1080
    assert meta["kvs"]["height"] == 1920
    assert meta["summary"] == "short vertical 1080p mov phone-video without audio"
    _validate_with_file(meta)


def test_parse_screen_recording_from_filename() -> None:
    meta = parse(
        _mp4_bytes(width=3840, height=2160),
        existing_meta=_base_meta("Screen Recording 2026-05-10.mp4"),
    )

    assert "screen-recording" in meta["tags"]
    assert "4k" in meta["tags"]
    assert "screen" in meta["keywords"]
    assert "recording" in meta["keywords"]
    _validate_with_file(meta)


def test_parse_video_never_raises_and_matches_parser_meta() -> None:
    meta = parse_video(content=b"not video", existing_meta=_base_meta())

    assert meta == empty_video_meta(existing_meta=_base_meta())
    _validate_with_file(meta)
