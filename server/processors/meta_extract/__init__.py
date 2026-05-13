"""Metadata extraction processor.

The `meta_extract` substrate parses File metadata from blob bytes when files
are created, replaced, copied, or renamed. It is the first warm-path processor
and the reference implementation for the substrate contract.
"""

from sqlalchemy.orm import Session

from processors.meta_extract import base
from processors.registry import ProcessorContext, register
from utils.logging import get_logger

log = get_logger(__name__)

KIND = "meta_extract"

DEFAULT_SUBSCRIBED_EVENT_TYPES = (
    "file.created",
    "file.updated",
    "file.copied",
    "file.moved",
)

VALID_EVENT_TYPES = DEFAULT_SUBSCRIBED_EVENT_TYPES


def handle(db: Session, ctx: ProcessorContext) -> None:
    event = ctx.file_event
    if event.file_id is None:
        log.info(
            "meta_extract_skipped_no_file_id",
            processor=ctx.processor_name,
            event_id=str(event.id),
            event_type=event.event_type,
        )
        return

    if event.event_type == "file.moved":
        from_name = (event.payload or {}).get("from_name")
        to_name = (event.payload or {}).get("to_name")
        if from_name == to_name:
            log.info(
                "meta_extract_skipped_move_no_rename",
                processor=ctx.processor_name,
                event_id=str(event.id),
                file_id=str(event.file_id),
            )
            return

    base.parse_file(db, event.file_id)


def register_substrate() -> None:
    register(
        kind=KIND,
        handler=handle,
        default_subscribed_event_types=DEFAULT_SUBSCRIBED_EVENT_TYPES,
        valid_event_types=VALID_EVENT_TYPES,
    )
