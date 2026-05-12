from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import settings as S
from .access_keys import router as access_keys_router
from .auth import router as auth_router
from .blobs import router as blobs_router
from .buckets import router as buckets_router
from .dependencies import require_admin, require_user
from .events import router as events_router
from .exception_handlers import register_exception_handlers
from .files import router as files_router
from .folder_access import router as folder_access_router
from .folders import router as folders_router
from .s3_gateway import router as s3_gateway_router
from .uploads import router as uploads_router
from .users import router as users_router

app = FastAPI(
    title="Relic API",
    description="API for the Relic system",
    version="0.1.0",
)
register_exception_handlers(app)

if S.S3_CORS_ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=S.S3_CORS_ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["ETag"],
    )


# Control plane (JSON, normal auth)
API_PREFIX = "/api"

app.include_router(auth_router, prefix=f"{API_PREFIX}/auth", tags=["auth"])
app.include_router(
    users_router,
    prefix=f"{API_PREFIX}/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    access_keys_router,
    prefix=f"{API_PREFIX}/access-keys",
    tags=["access-keys"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    buckets_router,
    prefix=f"{API_PREFIX}/buckets",
    tags=["buckets"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    folders_router,
    prefix=f"{API_PREFIX}/folders",
    tags=["folders"],
    dependencies=[Depends(require_user)],
)
app.include_router(
    folder_access_router,
    prefix=f"{API_PREFIX}/folder-access",
    tags=["folder-access"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    files_router,
    prefix=f"{API_PREFIX}/files",
    tags=["files"],
    dependencies=[Depends(require_user)],
)
app.include_router(
    uploads_router,
    prefix=f"{API_PREFIX}/uploads",
    tags=["uploads"],
    dependencies=[Depends(require_user)],
)
app.include_router(
    blobs_router,
    prefix=f"{API_PREFIX}/blobs",
    tags=["blobs"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    events_router,
    prefix=f"{API_PREFIX}/events",
    tags=["events"],
    dependencies=[Depends(require_admin)],
)

# S3 gateway (XML, SigV4 auth).
app.include_router(s3_gateway_router, prefix="/s3", tags=["s3"])


@app.get("/healthz")
def healthz():
    raise NotImplementedError("Not implemented")


@app.get("/readyz")
def readyz():
    raise NotImplementedError("Not implemented")
