import base64
import hashlib
import hmac
import json
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

import settings as S
from managers.exceptions import BadRequestError
from models import User
from utils.passwords import verify_password


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(password, user.password_hash):
        raise BadRequestError("Invalid email or password")

    return user


def create_session_token(user: User) -> str:
    payload = {
        "user_id": str(user.id),
        "exp": int(time.time()) + S.SESSION_MAX_AGE_SECONDS,
    }
    encoded_payload = encode_json(payload)
    signature = sign(encoded_payload)
    return f"{encoded_payload}.{signature}"


def get_session_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None

    payload = decode_session_token(token)
    if not payload:
        return None

    user_id = payload.get("user_id")
    if not isinstance(user_id, str):
        return None

    try:
        parsed_user_id = uuid.UUID(user_id)
    except ValueError:
        return None

    return db.get(User, parsed_user_id)


def decode_session_token(token: str) -> dict | None:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError:
        return None

    if not hmac.compare_digest(signature, sign(encoded_payload)):
        return None

    try:
        payload = json.loads(decode_base64(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None

    return payload


def encode_json(payload: dict) -> str:
    return encode_base64(json.dumps(payload, separators=(",", ":")).encode())


def encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign(value: str) -> str:
    digest = hmac.new(S.SESSION_SECRET.encode(), value.encode(), hashlib.sha256).digest()
    return encode_base64(digest)
