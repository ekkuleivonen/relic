from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import settings as S
from constants import API_PREFIX
from enums import HealthStatus
from database import DbSession
from processors.registry import init_builtin_substrates
from services import health as health_service
from .access_keys import router as access_keys_router
from .audit_events import router as audit_events_router
from .auth import router as auth_router
from .buckets import router as buckets_router
from .dependencies import require_admin, require_user
from .exception_handlers import register_exception_handlers
from .file_events import router as file_events_router
from .files import router as files_router
from .folder_access import router as folder_access_router
from .folders import router as folders_router
from .maintenance_events import router as maintenance_events_router
from .processors import router as processors_router
from .s3_gateway import router as s3_gateway_router
from .uploads import router as uploads_router
from .users import router as users_router

init_builtin_substrates()

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
    audit_events_router,
    prefix=f"{API_PREFIX}/audit-events",
    tags=["audit-events"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    file_events_router,
    prefix=f"{API_PREFIX}/file-events",
    tags=["file-events"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    maintenance_events_router,
    prefix=f"{API_PREFIX}/maintenance-events",
    tags=["maintenance-events"],
    dependencies=[Depends(require_admin)],
)
app.include_router(
    processors_router,
    prefix=f"{API_PREFIX}/processors",
    tags=["processors"],
    dependencies=[Depends(require_admin)],
)

# S3 gateway (XML, SigV4 auth).
app.include_router(s3_gateway_router, prefix="/s3", tags=["s3"])


@app.get("/healthz")
def healthz():
    return health_service.health_response()


@app.get("/readyz")
async def readyz(db: DbSession):
    payload = await health_service.readiness_response(db)
    if payload["status"] != HealthStatus.OK.value:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload,
        )
    return payload
