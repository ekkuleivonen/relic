"""Request-scoped context for use cases and audit emission."""

import uuid
from dataclasses import dataclass

from infra.db.models import User
from starlette.datastructures import Headers


@dataclass(frozen=True)
class Actor:
    id: uuid.UUID

    @classmethod
    def from_user(cls, user: User) -> "Actor":
        return cls(id=user.id)


@dataclass(frozen=True)
class EventContext:
    actor_id: uuid.UUID | None = None
    request_id: str | None = None


def request_id_from_headers(headers: Headers) -> str | None:
    return headers.get("x-request-id") or headers.get("x-correlation-id")


def context_from_headers(
    headers: Headers,
    *,
    actor_id: uuid.UUID | None = None,
) -> EventContext:
    return EventContext(
        actor_id=actor_id,
        request_id=request_id_from_headers(headers),
    )
