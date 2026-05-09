from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/users", tags=["users"])

"""
User management. Admin-only for create/delete/list; users can read and
update their own record.

Auth model is intentionally minimal for now (password hash on User).
Swap to OIDC/Authentik later by replacing the auth dependency, not these
routes.
"""


@router.get("/")
async def list_users(request: Request) -> Response:
    """
    GET /users -> list all users. Admin-only.
    Query params: ?limit=50&cursor=<id>&role=<int>
    """
    raise NotImplementedError


@router.post("/")
async def create_user(request: Request) -> Response:
    """
    POST /users -> create a new user. Admin-only.
    Body: { name, email, password, role }
    Returns the created User without password_hash.
    """
    raise NotImplementedError


@router.get("/me")
async def get_me(request: Request) -> Response:
    """
    GET /users/me -> the authenticated user's own record.
    Convenience endpoint; returns same shape as GET /users/{id}.
    """
    raise NotImplementedError


@router.get("/{user_id}")
async def get_user(user_id: str, request: Request) -> Response:
    """
    GET /users/{id} -> fetch a single user.
    Self or admin only.
    """
    raise NotImplementedError


@router.patch("/{user_id}")
async def update_user(user_id: str, request: Request) -> Response:
    """
    PATCH /users/{id} -> update mutable fields.
    Body: { name?, email?, role?, password? }
    Self can update name/email/password; only admin can change role.
    """
    raise NotImplementedError


@router.delete("/{user_id}")
async def delete_user(user_id: str, request: Request) -> Response:
    """
    DELETE /users/{id} -> hard delete. Admin-only.
    Cascades: revoke all access keys, drop folder access rows.
    Files owned/uploaded by user are NOT deleted; ownership becomes null.
    """
    raise NotImplementedError
