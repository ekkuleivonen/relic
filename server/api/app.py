from fastapi import Depends, FastAPI

from .access_keys import router as access_keys_router
from .auth import router as auth_router
from .blobs import router as blobs_router
from .dependencies import require_admin, require_user
from .exception_handlers import register_exception_handlers
from .files import router as files_router
from .folders import router as folders_router
from .s3_gateway import router as s3_gateway_router
from .buckets import router as buckets_router
from .users import router as users_router

app = FastAPI(
    title="Relic API",
    description="API for the Relic system",
    version="0.1.0",
)
register_exception_handlers(app)


# Control plane (JSON, normal auth)
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(
    users_router,
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    access_keys_router,
    prefix="/access-keys",
    tags=["access-keys"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    buckets_router,
    prefix="/buckets",
    tags=["buckets"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    folders_router,
    prefix="/folders",
    tags=["folders"],
    dependencies=[Depends(require_user)],
)
app.include_router(
    files_router,
    prefix="/files",
    tags=["files"],
    dependencies=[Depends(require_user)],
)
app.include_router(
    blobs_router,
    prefix="/blobs",
    tags=["blobs"],
    dependencies=[Depends(require_admin)],
)

# S3 gateway (XML, SigV4 auth). Keep this last because it owns catch-all paths.
app.include_router(s3_gateway_router, tags=["s3"])


@app.get("/healthz")
def healthz():
    raise NotImplementedError("Not implemented")


@app.get("/readyz")
def readyz():
    raise NotImplementedError("Not implemented")
