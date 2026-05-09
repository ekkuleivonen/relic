from typing import Any


class DomainError(Exception):
    status_code = 500

    def __init__(self, message: str, *, detail: Any | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail if detail is not None else message


class BadRequestError(DomainError):
    status_code = 400


class ResourceNotFound(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409
