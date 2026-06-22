"""Folder path composition."""

from __future__ import annotations

import uuid
from collections.abc import Mapping


def format_path_segment(prefix: str, name: str) -> str:
    """Compose a folder path. Root folder (empty name) renders as '/'."""
    if name == "":
        return "/"
    if prefix in ("", "/"):
        return f"/{name}"
    return f"{prefix}/{name}"


def build_folder_paths(
    parent_of: Mapping[uuid.UUID, uuid.UUID | None],
    name_of: Mapping[uuid.UUID, str],
) -> dict[uuid.UUID, str]:
    cache: dict[uuid.UUID, str] = {}

    def path_for(folder_id: uuid.UUID) -> str:
        if folder_id in cache:
            return cache[folder_id]

        segments: list[str] = []
        cursor: uuid.UUID | None = folder_id
        while cursor is not None and cursor not in cache:
            segments.append(name_of[cursor])
            cursor = parent_of[cursor]

        prefix = cache[cursor] if cursor is not None else ""
        path = prefix
        for name in reversed(segments):
            path = format_path_segment(path, name)
        cache[folder_id] = path
        return path

    return {folder_id: path_for(folder_id) for folder_id in parent_of}
