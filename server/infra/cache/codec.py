"""Serialize cache keys and values for tiered storage."""

from __future__ import annotations

import json
import uuid
from typing import Any

from infra.db.stores.folder_access_types import FolderTreeRow


def list_objects_cache_key(key: tuple[Any, ...]) -> str:
    return "|".join(str(part) for part in key)


def folder_tree_cache_key(scope: str) -> str:
    return scope


def folder_paths_cache_key(scope: str) -> str:
    return scope


def effective_permissions_cache_key(
    scope: str, user_id: uuid.UUID, required: int
) -> str:
    return f"{scope}:{user_id}:{required}"


def access_key_cache_key(scope: str, key_id: str) -> str:
    return f"{scope}:{key_id}"


def encode_text(value: str) -> bytes:
    return value.encode("utf-8")


def decode_text(value: bytes) -> str:
    return value.decode("utf-8")


def encode_folder_tree_rows(rows: tuple[FolderTreeRow, ...]) -> bytes:
    payload = [
        {"id": str(row.id), "parent_id": str(row.parent_id) if row.parent_id else None, "name": row.name}
        for row in rows
    ]
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def decode_folder_tree_rows(value: bytes) -> tuple[FolderTreeRow, ...]:
    payload = json.loads(value.decode("utf-8"))
    return tuple(
        FolderTreeRow(
            id=uuid.UUID(item["id"]),
            parent_id=uuid.UUID(item["parent_id"]) if item["parent_id"] else None,
            name=item["name"],
        )
        for item in payload
    )


def encode_uuid_str_map(values: dict[uuid.UUID, str]) -> bytes:
    payload = {str(key): value for key, value in values.items()}
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def decode_uuid_str_map(value: bytes) -> dict[uuid.UUID, str]:
    payload = json.loads(value.decode("utf-8"))
    return {uuid.UUID(key): item for key, item in payload.items()}


def encode_uuid_int_map(values: dict[uuid.UUID, int]) -> bytes:
    payload = {str(key): value for key, value in values.items()}
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def decode_uuid_int_map(value: bytes) -> dict[uuid.UUID, int]:
    payload = json.loads(value.decode("utf-8"))
    return {uuid.UUID(key): int(item) for key, item in payload.items()}
