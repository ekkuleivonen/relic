from fastapi import FastAPI

from .access_keys import router as access_keys_router
from .blobs import router as blobs_router
from .files import router as files_router
from .folders import router as folders_router
from .s3_gateway import router as s3_gateway_router
from .storages import router as storages_router
from .users import router as users_router

app = FastAPI()


# S3 gateway (XML, SigV4 auth)
app.include_router(s3_gateway_router, tags=["s3"])

# Control plane (JSON, normal auth)
app.include_router(users_router, prefix="/users", tags=["users"])
app.include_router(access_keys_router, prefix="/access-keys", tags=["access-keys"])
app.include_router(storages_router, prefix="/storages", tags=["storages"])
app.include_router(folders_router, prefix="/folders", tags=["folders"])
app.include_router(files_router, prefix="/files", tags=["files"])
app.include_router(blobs_router, prefix="/blobs", tags=["blobs"])


@app.get("/healthz")
def healthz():
    raise NotImplementedError("Not implemented")


@app.get("/readyz")
def readyz():
    raise NotImplementedError("Not implemented")
