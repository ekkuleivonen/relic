import asyncio
from contextlib import asynccontextmanager

from api.dependencies import UnitOfWorkDep
from api.openapi import API_DESCRIPTION, OPENAPI_TAGS, configure_openapi
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

import settings as S
from constants import API_PREFIX
from enums import HealthStatus
import infra.health as health
import infra.metrics as metrics
from infra.arq import close_arq_redis
from .access_keys import router as access_keys_router
from .auth import router as auth_router
from .storage_backends import router as storage_backends_router
from .dependencies import require_admin, require_user
from .exception_handlers import register_exception_handlers
from .filesystem_events import router as filesystem_events_router
from .files import router as files_router
from .folder_access import router as folder_access_router
from .folders import router as folders_router
from .audit_events import router as audit_events_router
from .blobs import router as blobs_router
from .s3_gateway import router as s3_gateway_router
from .uploads import router as uploads_router
from .users import router as users_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await close_arq_redis()


app = FastAPI(
    title="Pithosys API",
    description=API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS,
    swagger_ui_parameters={"persistAuthorization": True},
    lifespan=lifespan,
)
register_exception_handlers(app)
configure_openapi(app)


@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    path = request.url.path
    if path in {"/metrics", "/healthz", "/readyz"}:
        return await call_next(request)

    is_s3 = path.startswith("/s3")
    if not is_s3:
        metrics.API_INFLIGHT.inc()
    started_at = metrics.timer_start()
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if not is_s3:
            metrics.API_INFLIGHT.dec()
        if is_s3:
            metrics.observe_gateway_request(
                operation=_gateway_operation(request),
                status_code=status_code,
                started_at=started_at,
            )
        else:
            route = getattr(request.scope.get("route"), "path", path)
            metrics.observe_api_request(
                method=request.method,
                route=route,
                status_code=status_code,
                started_at=started_at,
            )

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
    storage_backends_router,
    prefix=f"{API_PREFIX}/storage-backends",
    tags=["storage-backends"],
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
    filesystem_events_router,
    prefix=f"{API_PREFIX}/filesystem-events",
    tags=["filesystem-events"],
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
    audit_events_router,
    prefix=f"{API_PREFIX}/audit-events",
    tags=["audit-events"],
    dependencies=[Depends(require_admin)],
)

# S3 gateway (XML, SigV4 auth).
app.include_router(s3_gateway_router, prefix="/s3", tags=["s3"])


@app.get("/healthz", tags=["health"], summary="Liveness probe")
def healthz():
    """Return process liveness. No authentication required."""
    return health.health_response()


@app.get("/readyz", tags=["health"], summary="Readiness probe")
async def readyz(uow: UnitOfWorkDep):
    """Return dependency readiness (Postgres, Redis, storage backends). No authentication required."""
    payload = await health.readiness_response(uow.session)
    if payload["status"] != HealthStatus.OK.value:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload,
        )
    return payload


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    body = await asyncio.to_thread(metrics.metrics_body)
    return Response(
        content=body,
        media_type=metrics.metrics_content_type(),
    )


def _gateway_operation(request: Request) -> str:
    path = request.url.path.removeprefix("/s3").strip("/")
    segments = [] if not path else path.split("/")
    query = request.query_params
    method = request.method.upper()

    if not segments:
        return "list_buckets"
    if len(segments) == 1:
        if method == "HEAD":
            return "head_bucket"
        if method == "GET" and "uploads" in query:
            return "list_multipart_uploads"
        if method == "GET":
            return "list_objects_v2"
        return "bucket_request"
    if method == "POST":
        return "create_multipart_upload" if "uploads" in query else "complete_multipart_upload"
    if method == "PUT":
        if "uploadId" in query:
            return "upload_part"
        if "x-amz-copy-source" in request.headers:
            return "copy_object"
        return "put_object"
    if method == "HEAD":
        return "head_object"
    if method == "GET":
        return "list_multipart_parts" if "uploadId" in query else "get_object"
    if method == "DELETE":
        return "abort_multipart_upload" if "uploadId" in query else "delete_object"
    return "object_request"
