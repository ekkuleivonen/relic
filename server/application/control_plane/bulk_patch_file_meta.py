import uuid
from dataclasses import dataclass

from application.context import Actor
from application.control_plane.patch_file_meta import patch_file_meta
from application.uow import UnitOfWork
from domain.exceptions import DomainError


@dataclass(frozen=True)
class BulkPatchFileMetaResult:
    patched_ids: list[uuid.UUID]
    errors: list[dict[str, str]]


def bulk_patch_file_meta(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_ids: list[uuid.UUID],
    patch: dict,
) -> BulkPatchFileMetaResult:
    patched_ids: list[uuid.UUID] = []
    errors: list[dict[str, str]] = []
    seen: set[uuid.UUID] = set()

    for file_id in file_ids:
        if file_id in seen:
            continue
        seen.add(file_id)
        try:
            patch_file_meta(uow, actor=actor, file_id=file_id, patch=patch)
            patched_ids.append(file_id)
        except DomainError as exc:
            errors.append(
                {
                    "file_id": str(file_id),
                    "code": exc.__class__.__name__,
                    "message": str(exc),
                }
            )

    return BulkPatchFileMetaResult(patched_ids=patched_ids, errors=errors)
