import uuid
from dataclasses import dataclass

from application.context import Actor
from application.control_plane.remove_file import remove_file_by_id
from application.uow import UnitOfWork
from domain.exceptions import DomainError
from enums import Permission


@dataclass(frozen=True)
class BulkDeleteFileResult:
    deleted_ids: list[uuid.UUID]
    errors: list[dict[str, str]]


def delete_file(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_id: uuid.UUID,
) -> None:
    remove_file_by_id(uow, actor=actor, file_id=file_id)


def bulk_delete_files(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_ids: list[uuid.UUID],
) -> BulkDeleteFileResult:
    deleted_ids: list[uuid.UUID] = []
    errors: list[dict[str, str]] = []
    seen: set[uuid.UUID] = set()

    for file_id in file_ids:
        if file_id in seen:
            continue
        seen.add(file_id)
        try:
            delete_file(uow, actor=actor, file_id=file_id)
            deleted_ids.append(file_id)
        except DomainError as exc:
            errors.append(
                {
                    "file_id": str(file_id),
                    "code": exc.__class__.__name__,
                    "message": str(exc),
                }
            )

    return BulkDeleteFileResult(deleted_ids=deleted_ids, errors=errors)
