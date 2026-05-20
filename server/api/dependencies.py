from collections.abc import Generator
from typing import Annotated

import settings as S
from application.uow import UnitOfWork
from composition import build_uow
from infra.db.engine import DbSession
from enums import UserRole
from fastapi import Cookie, Depends, Header, HTTPException, status
from application.control_plane import session_auth
from ports.entities import User


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


def require_user(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    session_token: Annotated[str | None, Cookie(alias=S.SESSION_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> User:
    request_id = x_request_id or x_correlation_id
    user, audited_failure = session_auth.get_authenticated_user(
        uow,
        session_token=session_token,
        authorization=authorization,
        request_id=request_id,
    )
    if not user:
        if audited_failure:
            uow.commit()
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
UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_uow)]
