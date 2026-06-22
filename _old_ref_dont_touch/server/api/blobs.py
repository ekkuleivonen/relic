import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import AdminUser, UnitOfWorkDep
from application.control_plane.gc_blobs import run_blob_gc

router = APIRouter()


class BlobGcResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scanned: int = Field(description="Blob rows examined.")
    deleted_rows: int = Field(description="Blob rows removed (refcount zero).")
    freed_bytes: int = Field(description="Logical bytes freed from storage.")
    errors: int = Field(description="Failures during object-store deletion.")


@router.post(
    "/gc",
    summary="Run blob garbage collection",
    description=(
        "Synchronously purge blobs with refcount zero from storage and the database. "
        "Normally handled by the worker; this endpoint is for manual admin runs."
    ),
)
async def trigger_gc(uow: UnitOfWorkDep, current_user: AdminUser) -> BlobGcResponse:
    del current_user
    result = run_blob_gc(uow, batch_id=uuid.uuid4())
    return BlobGcResponse(
        scanned=result["scanned"],
        deleted_rows=result["deleted_rows"],
        freed_bytes=result["freed_bytes"],
        errors=result["errors"],
    )
