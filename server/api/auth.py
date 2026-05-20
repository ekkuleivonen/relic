import datetime as dt
import uuid
from typing import Annotated

from api.dependencies import UnitOfWorkDep
from application.control_plane.auth_mutations import login as login_use_case
from application.control_plane.auth_mutations import logout as logout_use_case
from application.context import EventContext, request_id_from_headers
import settings as S
from enums import UserRole
from fastapi import APIRouter, Cookie, Request, Response, status
from domain.exceptions import BadRequestError
from pydantic import BaseModel, ConfigDict, Field
from infra.db.stores import auth

from api.dependencies import CurrentUser

router = APIRouter()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1)


class SessionUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    created_at: dt.datetime
    updated_at: dt.datetime


class SessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: SessionUserRead


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    uow: UnitOfWorkDep,
    request: Request,
) -> SessionRead:
    request_id = request_id_from_headers(request.headers)
    event_context = EventContext(request_id=request_id)
    try:
        user = login_use_case(
            uow,
            email=payload.email,
            password=payload.password,
            event_context=event_context,
        )
    except BadRequestError:
        raise
    response.set_cookie(
        key=S.SESSION_COOKIE_NAME,
        value=auth.create_session_token(user),
        max_age=S.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=S.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    return SessionRead(user=SessionUserRead.model_validate(user))


@router.post("/logout")
async def logout(
    response: Response,
    uow: UnitOfWorkDep,
    request: Request,
    session_token: Annotated[str | None, Cookie(alias=S.SESSION_COOKIE_NAME)] = None,
) -> Response:
    user = auth.get_session_user(uow.session, session_token)
    response.delete_cookie(
        key=S.SESSION_COOKIE_NAME,
        httponly=True,
        secure=S.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    logout_use_case(
        uow,
        user=user,
        event_context=EventContext(
            actor_id=user.id if user else None,
            request_id=request_id_from_headers(request.headers),
        ),
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/session")
async def get_session(current_user: CurrentUser) -> SessionRead:
    return SessionRead(user=SessionUserRead.model_validate(current_user))
