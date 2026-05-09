from fastapi import APIRouter, Request, Response

router = APIRouter()

"""
Storage backend management. Admin-only across the board - storages are
infrastructure, not user data.

The credential fields go in K8s secrets (Storage.secret_ref); these routes
manage everything else (endpoint, region, tier, capacity tracking, etc.).
"""


@router.get("/")
async def list_storages(request: Request) -> Response:
    """
    GET /storages -> list all configured storages.
    Includes capacity/usage/latency snapshots from the most recent probe.
    """
    raise NotImplementedError


@router.post("/")
async def create_storage(request: Request) -> Response:
    """
    POST /storages -> register a new storage backend.
    Body: { name, endpoint, region, secret_ref, tier, headroom_pct? }
    Initial capacity/usage/latency are null until first probe runs.
    """
    raise NotImplementedError


@router.get("/{storage_id}")
async def get_storage(storage_id: str, request: Request) -> Response:
    """
    GET /storages/{id} -> single storage with capacity/usage/latency.
    """
    raise NotImplementedError


@router.patch("/{storage_id}")
async def update_storage(storage_id: str, request: Request) -> Response:
    """
    PATCH /storages/{id} -> update mutable fields.
    Body: { name?, tier?, headroom_pct?, secret_ref? }
    endpoint/region are immutable - register a new storage instead.
    """
    raise NotImplementedError


@router.delete("/{storage_id}")
async def delete_storage(storage_id: str, request: Request) -> Response:
    """
    DELETE /storages/{id} -> remove a storage backend.
    Refuses if any Blobs still reference it; migrate them out first.
    Returns 409 with blob count if the constraint blocks.
    """
    raise NotImplementedError


@router.post("/{storage_id}/probe")
async def probe_storage(storage_id: str, request: Request) -> Response:
    """
    POST /storages/{id}/probe -> trigger an immediate capacity/latency probe.
    Returns the fresh snapshot. Useful after capacity changes or for debugging.
    Normally a cron job does this; this is the manual override.
    """
    raise NotImplementedError


@router.post("/{storage_id}/drain")
async def drain_storage(storage_id: str, request: Request) -> Response:
    """
    POST /storages/{id}/drain -> mark for draining; migrate all blobs to
    other storages of the same or compatible tier in the background.
    Status is queryable via GET /storages/{id}.
    Used when retiring a storage backend.
    """
    raise NotImplementedError
