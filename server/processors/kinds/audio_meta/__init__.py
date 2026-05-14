"""Audio metadata processor."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.audio_meta.parser import parse_audio
from processors.type_meta import TypeMetaProcessor


class AudioMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AudioMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "audio_meta"
    display_name: ClassVar[str] = "Audio metadata"
    description: ClassVar[str] = (
        "Reads container, codec, duration and tag metadata from audio files."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:audio_meta"
    default_concurrency: ClassVar[int] = 4
    max_concurrency: ClassVar[int] = 16

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("audio/",)
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("audio/",)
    default_extensions: ClassVar[tuple[str, ...]] = ()
    valid_extensions: ClassVar[tuple[str, ...]] = (
        "aac",
        "aif",
        "aiff",
        "flac",
        "m4a",
        "mp3",
        "oga",
        "ogg",
        "opus",
        "wav",
    )

    config_model: ClassVar[type[BaseModel]] = AudioMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.AUDIO_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_audio(content=content, file_info=file_info)


__all__ = ["AudioMetaConfig", "AudioMetaProcessor"]
