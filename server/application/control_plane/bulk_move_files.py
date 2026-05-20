import uuid
from dataclasses import dataclass

from application.context import Actor
from application.control_plane.move_file import move_file
from application.uow import UnitOfWork
from domain.exceptions import DomainError


@dataclass(frozen=True)
class BulkMoveFileResult:
    moved_ids: list[uuid.UUID]
    errors: list[dict[str, str]]


def bulk_move_files(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_ids: list[uuid.UUID],
    destination_folder_id: uuid.UUID,
    name: str | None = None,
) -> BulkMoveFileResult:
    moved_ids: list[uuid.UUID] = []
    errors: list[dict[str, str]] = []
    seen: set[uuid.UUID] = set()

    for file_id in file_ids:
        if file_id in seen:
            continue
        seen.add(file_id)
        try:
            move_file(
                uow,
                actor=actor,
                file_id=file_id,
                destination_folder_id=destination_folder_id,
                name=name,
            )
            moved_ids.append(file_id)
        except DomainError as exc:
            errors.append(
                {
                    "file_id": str(file_id),
                    "code": exc.__class__.__name__,
                    "message": str(exc),
                }
            )

    return BulkMoveFileResult(moved_ids=moved_ids, errors=errors)
