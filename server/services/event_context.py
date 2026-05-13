"""Shared request-scoped context for event emission.

Both ``audit_events`` and ``file_events`` carry the same two correlation
fields on every write — the acting user (if any) and the originating
request id. We carry them through service calls as a single dataclass so
the API layer never has to pick between "audit" and "file" context types,
and so service functions can write either kind of event from one input.

System-emitted writes (workers, dispatcher, cron) pass ``None`` for both
fields; ``actor_user_id`` is the canonical "this was a user-triggered
mutation" signal.
"""

import uuid
from dataclasses import dataclass

from starlette.datastructures import Headers


@dataclass(frozen=True)
class EventContext:
    actor_user_id: uuid.UUID | None = None
    request_id: str | None = None


def request_id_from_headers(headers: Headers) -> str | None:
    return headers.get("x-request-id") or headers.get("x-correlation-id")


def context_from_headers(
    headers: Headers,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> EventContext:
    return EventContext(
        actor_user_id=actor_user_id,
        request_id=request_id_from_headers(headers),
    )
