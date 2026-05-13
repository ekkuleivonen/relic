"""Central configuration loaded from environment variables, grouped by subsystem."""

from utils.environ import env
from utils.logging import configure_logging

# =============================================================================
# Logging
# =============================================================================

LOG_LEVEL: str = env.str("LOG_LEVEL", default="INFO")
SILENCE_LOGGERS: list[str] = env.list(
    "SILENCE_LOGGERS",
    default=[
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "fastapi",
        "httpx",
        "httpcore",
        "urllib3",
        "asyncio",
    ],
)
configure_logging(
    log_level=LOG_LEVEL,
    silence=SILENCE_LOGGERS,
)

# =============================================================================
# Postgres
# =============================================================================

POSTGRES_HOST: str = env.str("POSTGRES_HOST", default="localhost")
POSTGRES_PORT: int = env.int("POSTGRES_PORT", default=5432)
POSTGRES_DB: str = env.str("POSTGRES_DB", default="relic")
POSTGRES_USER: str = env.str("POSTGRES_USER", default="relic")
POSTGRES_PASSWORD: str = env.str("POSTGRES_PASSWORD", default="relic")

# =============================================================================
# Encryption
# =============================================================================

ENCRYPTION_SECRET: str = env.str(
    "ENCRYPTION_SECRET",
    default="dev-encryption-secret-change-me",
)

# =============================================================================
# Seed Data
# =============================================================================

RELIC_ADMIN_NAME: str = env.str("RELIC_ADMIN_NAME", default="Relic Admin")
RELIC_ADMIN_EMAIL: str = env.str("RELIC_ADMIN_EMAIL", default="admin@relic.local")
RELIC_ADMIN_PASSWORD: str = env.str("RELIC_ADMIN_PASSWORD", default="relic-admin")

# =============================================================================
# Sessions
# =============================================================================

SESSION_SECRET: str = env.str("SESSION_SECRET", default=ENCRYPTION_SECRET)
SESSION_COOKIE_NAME: str = env.str("SESSION_COOKIE_NAME", default="relic_session")
SESSION_MAX_AGE_SECONDS: int = env.int(
    "SESSION_MAX_AGE_SECONDS", default=60 * 60 * 24 * 7
)
SESSION_COOKIE_SECURE: bool = env.bool("SESSION_COOKIE_SECURE", default=False)

# =============================================================================
# S3 Gateway Signing
# =============================================================================

RELIC_SIGNING_TTL_SECONDS: int = env.int("RELIC_SIGNING_TTL_SECONDS", default=300)
RELIC_SIGNING_REGION: str = env.str("RELIC_SIGNING_REGION", default="relic")

_SIGNING_KEY_ID: str = env.str("RELIC_SIGNING_KEY_ID", default="relic-dev")
_SIGNING_SECRET: str = env.str(
    "RELIC_SIGNING_SECRET",
    default=f"{ENCRYPTION_SECRET}:s3-signing",
)
RELIC_SIGNING_KEYS: dict[str, str] = env.json(
    "RELIC_SIGNING_KEYS",
    default={_SIGNING_KEY_ID: _SIGNING_SECRET},
)
RELIC_SIGNING_CURRENT_KEY_ID: str = env.str(
    "RELIC_SIGNING_CURRENT_KEY_ID",
    default=_SIGNING_KEY_ID,
)

if RELIC_SIGNING_CURRENT_KEY_ID not in RELIC_SIGNING_KEYS:
    raise ValueError("RELIC_SIGNING_CURRENT_KEY_ID must exist in RELIC_SIGNING_KEYS")

S3_CORS_ALLOWED_ORIGINS: list[str] = env.list("S3_CORS_ALLOWED_ORIGINS", default=[])
UPLOAD_SPOOL_MAX_MEMORY_BYTES: int = env.int(
    "UPLOAD_SPOOL_MAX_MEMORY_BYTES",
    default=8 * 1024 * 1024,
)

# =============================================================================
# meta_extract toolchain byte caps
# =============================================================================
# Per-toolchain hard caps on bytes fetched from object storage during the
# warm-path meta_extract substrate run. Each toolchain reads up to its cap via
# a single S3 Range GET; files larger than the cap are parsed from the
# truncated prefix (and the substrate logs ``*_meta_extract_truncated``).

IMAGE_META_EXTRACT_MAX_BYTES: int = env.int(
    "IMAGE_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

TABULAR_META_EXTRACT_MAX_BYTES: int = env.int(
    "TABULAR_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

PARQUET_META_EXTRACT_MAX_BYTES: int = env.int(
    "PARQUET_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

JSON_META_EXTRACT_MAX_BYTES: int = env.int(
    "JSON_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

PDF_META_EXTRACT_MAX_BYTES: int = env.int(
    "PDF_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

TEXT_META_EXTRACT_MAX_BYTES: int = env.int(
    "TEXT_META_EXTRACT_MAX_BYTES",
    default=16 * 1024 * 1024,
)

AUDIO_META_EXTRACT_MAX_BYTES: int = env.int(
    "AUDIO_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

VIDEO_META_EXTRACT_MAX_BYTES: int = env.int(
    "VIDEO_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

ARCHIVE_META_EXTRACT_MAX_BYTES: int = env.int(
    "ARCHIVE_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

OFFICE_DOC_META_EXTRACT_MAX_BYTES: int = env.int(
    "OFFICE_DOC_META_EXTRACT_MAX_BYTES",
    default=128 * 1024 * 1024,
)

HTML_META_EXTRACT_MAX_BYTES: int = env.int(
    "HTML_META_EXTRACT_MAX_BYTES",
    default=16 * 1024 * 1024,
)

REDIS_HOST: str = env.str("REDIS_HOST", default="localhost")
REDIS_PORT: int = env.int("REDIS_PORT", default=6379)
REDIS_PASSWORD: str = env.str("REDIS_PASSWORD", default="replace_me")
PROCESSING_QUEUE_NAME: str = env.str(
    "PROCESSING_QUEUE_NAME",
    default="relic:processing",
)
MAINTENANCE_QUEUE_NAME: str = env.str(
    "MAINTENANCE_QUEUE_NAME",
    default="relic:maintenance",
)

# Dispatcher (warm-path pull loop; see processors/dispatcher.py)
DISPATCHER_BATCH_SIZE: int = env.int("DISPATCHER_BATCH_SIZE", default=100)
DISPATCHER_SAFETY_INTERVAL_SECONDS: int = env.int(
    "DISPATCHER_SAFETY_INTERVAL_SECONDS",
    default=15,
)
DISPATCHER_LISTEN_BACKOFF_SECONDS: int = env.int(
    "DISPATCHER_LISTEN_BACKOFF_SECONDS",
    default=2,
)

# Storage maintenance (arq cron + jobs; see processors/worker_maintenance.py)
EVENT_RETENTION_DAYS: int = env.int("EVENT_RETENTION_DAYS", default=90)
STORAGE_MAINTENANCE_PURGE_BATCH: int = env.int(
    "STORAGE_MAINTENANCE_PURGE_BATCH",
    default=80,
)
STORAGE_MAINTENANCE_MIGRATE_BATCH: int = env.int(
    "STORAGE_MAINTENANCE_MIGRATE_BATCH",
    default=24,
)
STORAGE_MAINTENANCE_BUCKET_PRESSURE_RATIO: float = env.float(
    "STORAGE_MAINTENANCE_BUCKET_PRESSURE_RATIO",
    default=0.85,
)
