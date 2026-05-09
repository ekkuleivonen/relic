from fastapi import FastAPI

from .access_keys import router as access_keys_router
from .blobs import router as blobs_router
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
app.include_router(users_router, prefix="/users", tags=["users"])
app.include_router(access_keys_router, prefix="/access-keys", tags=["access-keys"])
app.include_router(buckets_router, prefix="/buckets", tags=["buckets"])
app.include_router(folders_router, prefix="/folders", tags=["folders"])
app.include_router(files_router, prefix="/files", tags=["files"])
app.include_router(blobs_router, prefix="/blobs", tags=["blobs"])

# S3 gateway (XML, SigV4 auth). Keep this last because it owns catch-all paths.
app.include_router(s3_gateway_router, tags=["s3"])


@app.get("/healthz")
def healthz():
    raise NotImplementedError("Not implemented")


@app.get("/readyz")
def readyz():
    raise NotImplementedError("Not implemented")
