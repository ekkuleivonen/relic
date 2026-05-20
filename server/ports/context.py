"""Shared request/actor context types (no I/O)."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    id: uuid.UUID


@dataclass(frozen=True)
class EventContext:
    actor_id: uuid.UUID | None = None
    request_id: str | None = None
