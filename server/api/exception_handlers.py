from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from managers.exceptions import (
    BadRequestError,
    ConflictError,
    PermissionDenied,
    ResourceNotFound,
)
from utils.logging import get_logger

log = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BadRequestError, handle_domain_error)
    app.add_exception_handler(PermissionDenied, handle_domain_error)
    app.add_exception_handler(ResourceNotFound, handle_domain_error)
    app.add_exception_handler(ConflictError, handle_domain_error)


async def handle_domain_error(request: Request, exc):
    log.info(
        "domain_error",
        path=str(request.url.path),
        error=exc.__class__.__name__,
        detail=exc.detail,
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
