import uuid

from infra.maintenance.storage import purge_dereferenced_blobs_batch
from application.uow import UnitOfWork

import settings as S


def run_blob_gc(uow: UnitOfWork, *, batch_id: uuid.UUID | None = None) -> dict:
    return purge_dereferenced_blobs_batch(
        uow,
        batch=S.STORAGE_MAINTENANCE_PURGE_BATCH,
        batch_id=batch_id,
    )
