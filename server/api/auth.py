import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status
from pydantic import BaseModel, ConfigDict, Field

import settings as S
from managers.exceptions import BadRequestError
from api.dependencies import CurrentUser
from database import DbSession
from schema_plan import UserRole
from services import auth as auth_service
from services import events as event_service

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
async def login(payload: LoginRequest, response: Response, db: DbSession) -> SessionRead:
    try:
        user = auth_service.authenticate_user(
            db,
            email=payload.email,
            password=payload.password,
        )
    except BadRequestError:
        event_service.record_event(
            db,
            source="relic_api",
            operation="auth.login.failed",
            status="failed",
            metadata={"email": payload.email.lower()},
        )
        raise
    response.set_cookie(
        key=S.SESSION_COOKIE_NAME,
        value=auth_service.create_session_token(user),
        max_age=S.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=S.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    event_service.record_event(
        db,
        source="relic_api",
        operation="auth.login.succeeded",
        actor_user_id=user.id,
        metadata={"email": user.email},
    )
    return SessionRead(user=SessionUserRead.model_validate(user))


@router.post("/logout")
async def logout(
    response: Response,
    db: DbSession,
    session_token: Annotated[str | None, Cookie(alias=S.SESSION_COOKIE_NAME)] = None,
) -> Response:
    user = auth_service.get_session_user(db, session_token)
    response.delete_cookie(
        key=S.SESSION_COOKIE_NAME,
        httponly=True,
        secure=S.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    event_service.record_event(
        db,
        source="relic_api",
        operation="auth.logout",
        actor_user_id=user.id if user else None,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/session")
async def get_session(current_user: CurrentUser) -> SessionRead:
    return SessionRead(user=SessionUserRead.model_validate(current_user))
