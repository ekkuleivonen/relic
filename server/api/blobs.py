import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from api.dependencies import AdminUser, UnitOfWorkDep
from application.control_plane.gc_blobs import run_blob_gc

router = APIRouter()


class BlobGcResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scanned: int
    deleted_rows: int
    freed_bytes: int
    errors: int


@router.post("/gc")
async def trigger_gc(uow: UnitOfWorkDep, current_user: AdminUser) -> BlobGcResponse:
    del current_user
    result = run_blob_gc(uow, batch_id=uuid.uuid4())
    return BlobGcResponse(
        scanned=result["scanned"],
        deleted_rows=result["deleted_rows"],
        freed_bytes=result["freed_bytes"],
        errors=result["errors"],
    )
