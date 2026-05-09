import datetime as dt
import uuid

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field

import settings as S
from api.dependencies import CurrentUser
from database import DbSession
from schema_plan import UserRole
from services import auth as auth_service

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
    user = auth_service.authenticate_user(
        db,
        email=payload.email,
        password=payload.password,
    )
    response.set_cookie(
        key=S.SESSION_COOKIE_NAME,
        value=auth_service.create_session_token(user),
        max_age=S.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=S.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    return SessionRead(user=SessionUserRead.model_validate(user))


@router.post("/logout")
async def logout(response: Response) -> Response:
    response.delete_cookie(
        key=S.SESSION_COOKIE_NAME,
        httponly=True,
        secure=S.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/session")
async def get_session(current_user: CurrentUser) -> SessionRead:
    return SessionRead(user=SessionUserRead.model_validate(current_user))
