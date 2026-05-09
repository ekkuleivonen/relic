import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

import settings as S


@lru_cache
def get_fernet() -> Fernet:
    key = hashlib.sha256(S.ENCRYPTION_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_string(value: str) -> str:
    return get_fernet().encrypt(value.encode()).decode()


def decrypt_string(value: str) -> str:
    return get_fernet().decrypt(value.encode()).decode()
