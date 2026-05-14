"""Video metadata processor."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.video_meta.parser import parse_video
from processors.type_meta import TypeMetaProcessor


class VideoMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "video_meta"
    display_name: ClassVar[str] = "Video metadata"
    description: ClassVar[str] = (
        "Reads container and stream metadata from video files."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:video_meta"
    default_concurrency: ClassVar[int] = 2
    max_concurrency: ClassVar[int] = 8

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("video/",)
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("video/",)
    default_extensions: ClassVar[tuple[str, ...]] = ()
    valid_extensions: ClassVar[tuple[str, ...]] = (
        "avi",
        "mkv",
        "mov",
        "mp4",
        "webm",
    )

    config_model: ClassVar[type[BaseModel]] = VideoMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.VIDEO_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_video(content=content, file_info=file_info)


__all__ = ["VideoMetaConfig", "VideoMetaProcessor"]
