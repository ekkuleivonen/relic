from fastapi import APIRouter, Request, Response

router = APIRouter()

"""
S3 access keys. Each key belongs to a user and inherits that user's
folder permissions for SigV4-authenticated requests at the S3 gateway.

Secret is shown ONCE at creation, then only the hash is stored.
"""


@router.get("/")
async def list_access_keys(request: Request) -> Response:
    """
    GET /access-keys -> list keys.
    Self sees own keys; admin sees all (?user_id= filter).
    Never returns the secret, only key_id, name, last_used_at, revoked_at.
    """
    raise NotImplementedError


@router.post("/")
async def create_access_key(request: Request) -> Response:
    """
    POST /access-keys -> mint a new access key.
    Body: { name, user_id? }   (user_id admin-only; defaults to self)
    Returns: { id, key_id, secret_access_key, name, ... }
    The secret is in the response body and CANNOT be retrieved later.
    """
    raise NotImplementedError


@router.get("/{key_id}")
async def get_access_key(key_id: str, request: Request) -> Response:
    """
    GET /access-keys/{id} -> metadata for one key.
    Self for own; admin for any. Secret never included.
    """
    raise NotImplementedError


@router.post("/{key_id}/revoke")
async def revoke_access_key(key_id: str, request: Request) -> Response:
    """
    POST /access-keys/{id}/revoke -> set revoked_at to now.
    Idempotent. Revoked keys are kept for audit; use DELETE to remove.
    """
    raise NotImplementedError


@router.delete("/{key_id}")
async def delete_access_key(key_id: str, request: Request) -> Response:
    """
    DELETE /access-keys/{id} -> hard delete the key row.
    Self for own; admin for any.
    """
    raise NotImplementedError
