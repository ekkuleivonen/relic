"""Request-scoped context for use cases and audit emission."""

import uuid

from infra.db.models import User
from ports.context import Actor, EventContext
from starlette.datastructures import Headers


def actor_from_user(user: User) -> Actor:
    return Actor(id=user.id)


# Backwards-compatible alias used across the codebase.
Actor.from_user = classmethod(  # type: ignore[method-assign,attr-defined]
    lambda cls, user: cls(id=user.id)
)


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
