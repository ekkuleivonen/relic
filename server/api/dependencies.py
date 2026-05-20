from collections.abc import Generator
from typing import Annotated

import settings as S
from application.uow import UnitOfWork
from composition import build_uow
from infra.db.engine import DbSession
from enums import UserRole
from fastapi import Cookie, Depends, HTTPException, status
from infra.db.models import User
from application.control_plane import auth


def require_user(
    db: DbSession,
    session_token: Annotated[str | None, Cookie(alias=S.SESSION_COOKIE_NAME)] = None,
) -> User:
    user = auth.get_session_user(db, session_token)
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


def get_uow(db: DbSession) -> Generator[UnitOfWork, None, None]:
    uow = build_uow(db)
    try:
        yield uow
        uow.commit()
    except Exception:
        uow.rollback()
        raise
    finally:
        uow.close()


CurrentUser = Annotated[User, Depends(require_user)]
AdminUser = Annotated[User, Depends(require_admin)]
UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_uow)]
