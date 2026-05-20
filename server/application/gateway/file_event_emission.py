"""Map gateway put/multipart results to file event emissions."""

from application.control_plane import file_event_emission
from application.uow import UnitOfWork
from infra.gateway.object_multipart import CompleteMultipartResult
from infra.gateway.object_types import PutObjectResult
from ports.entities import User


def emit_put_object_events(
    uow: UnitOfWork,
    *,
    result: PutObjectResult,
    current_user: User,
    origin: str,
) -> None:
    if result.created:
        file_event_emission.emit_file_created(
            uow,
            file=result.file,
            blob=result.blob,
            origin=origin,
            actor_id=current_user.id,
        )
        return

    if (
        result.previous_blob_id is not None
        and result.previous_blob_id != result.blob.id
    ):
        file_event_emission.emit_file_content_updated(
            uow,
            file=result.file,
            blob=result.blob,
            previous_blob_id=result.previous_blob_id,
            actor_id=current_user.id,
        )


def emit_multipart_complete_events(
    uow: UnitOfWork,
    *,
    result: CompleteMultipartResult,
    current_user: User,
) -> None:
    if result.file is None or result.blob is None:
        return
    emit_put_object_events(
        uow,
        result=PutObjectResult(
            file=result.file,
            blob=result.blob,
            etag=result.etag,
            created=result.created,
            previous_blob_id=result.previous_blob_id,
        ),
        current_user=current_user,
        origin="multipart",
    )
