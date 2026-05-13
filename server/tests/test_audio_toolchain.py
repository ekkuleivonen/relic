"""Tests for processors.meta_extract.toolchains.audio."""

import io
import wave

from mutagen.id3 import TALB, TCON, TDRC, TIT2, TPE1, TRCK
from mutagen.wave import WAVE

from domain.files.meta import FileMeta, build_file_meta
from processors.meta_extract.toolchains.audio import empty_audio_meta, parse, parse_audio


def _base_meta(file_name: str = "x.wav", mimetype: str = "audio/wav") -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype=mimetype,
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def _wav_bytes(*, channels: int = 1, seconds: int = 1) -> bytes:
    buf = io.BytesIO()
    sample_rate = 8000
    with wave.open(buf, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * channels * sample_rate * seconds)
    return buf.getvalue()


def _tagged_wav_bytes() -> bytes:
    content = _wav_bytes(channels=2, seconds=1)
    audio = WAVE(io.BytesIO(content))
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["Everything In Its Right Place"]))
    audio.tags.add(TPE1(encoding=3, text=["Radiohead"]))
    audio.tags.add(TALB(encoding=3, text=["Kid A"]))
    audio.tags.add(TCON(encoding=3, text=["Alternative"]))
    audio.tags.add(TDRC(encoding=3, text=["2000"]))
    audio.tags.add(TRCK(encoding=3, text=["1/10"]))
    out = io.BytesIO(content)
    audio.save(out)
    return out.getvalue()


def test_parse_wav_duration_channels_and_lossless() -> None:
    meta = parse(_wav_bytes(), existing_meta=_base_meta())

    assert meta["tags"] == ["audio", "wav", "lossless", "mono", "short"]
    assert meta["keywords"] == ["wav", "pcm"]
    assert meta["kvs"]["duration_seconds"] == 1.0
    assert meta["summary"] == "short mono wav audio"
    _validate_with_file(meta)


def test_parse_tagged_music_promotes_labels() -> None:
    meta = parse(_tagged_wav_bytes(), existing_meta=_base_meta("radiohead.wav"))

    assert meta["tags"] == ["audio", "wav", "music", "lossless", "stereo", "short"]
    assert meta["keywords"] == [
        "everything in its right place",
        "radiohead",
        "kid a",
        "alternative",
        "2000",
        "1/10",
        "wav",
        "pcm",
    ]
    assert meta["summary"] == "short stereo wav music by radiohead"
    _validate_with_file(meta)


def test_parse_podcast_hint_from_filename() -> None:
    meta = parse(
        _wav_bytes(channels=1, seconds=1),
        existing_meta=_base_meta("daily-podcast-episode.wav"),
    )

    assert "podcast" in meta["tags"]
    assert "daily" in meta["keywords"]
    assert "podcast" in meta["keywords"]
    assert "episode" in meta["keywords"]
    assert meta["summary"] == "short mono wav podcast"
    _validate_with_file(meta)


def test_parse_audio_never_raises_and_matches_parser_meta() -> None:
    meta = parse_audio(content=b"not audio", existing_meta=_base_meta("x.mp3", "audio/mpeg"))

    assert meta == empty_audio_meta(existing_meta=_base_meta("x.mp3", "audio/mpeg"))
    _validate_with_file(meta)
