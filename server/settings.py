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
S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS: int = env.int(
    "S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS",
    default=24,
)
S3_HOTPATH_METADATA_CACHE_TTL_SECONDS: int = env.int(
    "S3_HOTPATH_METADATA_CACHE_TTL_SECONDS",
    default=120,
)
S3_LIST_OBJECTS_CACHE_TTL_SECONDS: int = env.int(
    "S3_LIST_OBJECTS_CACHE_TTL_SECONDS",
    default=15,
)
S3_ACCESS_KEY_CACHE_TTL_SECONDS: int = env.int(
    "S3_ACCESS_KEY_CACHE_TTL_SECONDS",
    default=120,
)
S3_ACCESS_KEY_LAST_USED_DEBOUNCE_SECONDS: int = env.int(
    "S3_ACCESS_KEY_LAST_USED_DEBOUNCE_SECONDS",
    default=60,
)

# =============================================================================
# meta_extract toolchain byte caps
# =============================================================================
# Per-toolchain hard caps on bytes fetched from object storage during the
# warm-path meta_extract processor run. Each toolchain reads up to its cap via
# a single S3 Range GET; files larger than the cap are parsed from the
# truncated prefix (and the processor logs ``*_meta_extract_truncated``).

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

# ---------------------------------------------------------------------------
# Latency-driven automatic tiering
# ---------------------------------------------------------------------------
# The cron has two independent ticks:
#
# * Demote: if the hottest bucket holding a blob is full (current/max ratio
#   >= STORAGE_DEMOTION_PRESSURE_RATIO), oldest-by-accessed_at blobs spill
#   into the next-hottest bucket with capacity.
# * Promote: blobs whose accessed_at is within STORAGE_PROMOTION_RECENCY_DAYS
#   bubble up toward the hottest bucket whose post-move usage would stay
#   under STORAGE_PROMOTION_HEADROOM_RATIO.
#
# Hysteresis: promotion_headroom_ratio < demotion_pressure_ratio prevents
# ping-ponging. STORAGE_MIGRATION_MIN_RESIDENCY_HOURS adds a per-blob cooloff
# after a successful migration so we never bounce the same blob twice in a
# tick window.
#
# STORAGE_WRITE_HEADROOM_RATIO is enforced at upload time (placement.choose_bucket)
# to leave breathing room for the demote cron - never fill a bucket all the way
# from the user write path.

STORAGE_DEMOTION_PRESSURE_RATIO: float = env.float(
    "STORAGE_DEMOTION_PRESSURE_RATIO",
    default=0.85,
)
STORAGE_PROMOTION_HEADROOM_RATIO: float = env.float(
    "STORAGE_PROMOTION_HEADROOM_RATIO",
    default=0.70,
)
STORAGE_PROMOTION_RECENCY_DAYS: int = env.int(
    "STORAGE_PROMOTION_RECENCY_DAYS",
    default=7,
)
STORAGE_MIGRATION_MIN_RESIDENCY_HOURS: int = env.int(
    "STORAGE_MIGRATION_MIN_RESIDENCY_HOURS",
    default=6,
)
STORAGE_WRITE_HEADROOM_RATIO: float = env.float(
    "STORAGE_WRITE_HEADROOM_RATIO",
    default=0.95,
)
STORAGE_DEMOTE_BATCH: int = env.int("STORAGE_DEMOTE_BATCH", default=24)
STORAGE_PROMOTE_BATCH: int = env.int("STORAGE_PROMOTE_BATCH", default=24)

# Hotness ranking averages over the last N successful probes per bucket so a
# single noisy sample can't reorder buckets.
PROBE_RANKING_WINDOW: int = env.int("PROBE_RANKING_WINDOW", default=3)
# How long we keep historical bucket_probes rows (trimmed by maintenance cron).
PROBES_RETENTION_DAYS: int = env.int("PROBES_RETENTION_DAYS", default=14)

# accessed_at update debounce: only bump on read if the previous bump was
# longer ago than this. Keeps high-QPS GET/HEAD traffic from beating the
# blobs row to death.
ACCESS_TOUCH_DEBOUNCE_MINUTES: int = env.int(
    "ACCESS_TOUCH_DEBOUNCE_MINUTES",
    default=5,
)
