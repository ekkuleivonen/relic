"""Structured JSON logging configuration.

Handles BOTH structlog loggers (get_logger) and stdlib loggers
(logging.getLogger) so all output is consistent JSON.
"""

import logging
import sys
from typing import Optional

import structlog

_shared_processors: list[structlog.types.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
]

_structlog_configured = False


def configure_logging(
    log_level: str = "INFO",
    silence: Optional[list[str]] = None,
) -> None:
    global _structlog_configured
    if _structlog_configured:
        return

    level = getattr(logging, log_level.upper(), logging.INFO)

    if silence is None:
        # Lazy import: settings imports configure_logging; avoid circular import at module load.
        import settings as S

        silence = S.SILENCE_LOGGERS

    # Formatter that renders ALL log records (structlog + stdlib) as JSON
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root.addHandler(handler)

    for name in silence:
        logger = logging.getLogger(name)
        logger.setLevel(logging.ERROR)
        logger.propagate = False

    structlog.configure(
        processors=_shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
