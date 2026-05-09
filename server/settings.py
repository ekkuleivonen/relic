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
# Database
# =============================================================================

DATABASE_URL: str = env.str(
    "DATABASE_URL",
    default=env.str(
        "DATABASE_URL",
        default="postgresql://relic:relic@localhost:5432/relic",
    ),
)

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
SESSION_MAX_AGE_SECONDS: int = env.int("SESSION_MAX_AGE_SECONDS", default=60 * 60 * 24 * 7)
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
