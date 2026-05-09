from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status

import settings as S
from database import DbSession
from models import User
from schema_plan import UserRole
from services import auth as auth_service


def require_user(
    db: DbSession,
    session_token: Annotated[str | None, Cookie(alias=S.SESSION_COOKIE_NAME)] = None,
) -> User:
    user = auth_service.get_session_user(db, session_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return user


def require_admin(current_user: Annotated[User, Depends(require_user)]) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user


CurrentUser = Annotated[User, Depends(require_user)]
AdminUser = Annotated[User, Depends(require_admin)]
