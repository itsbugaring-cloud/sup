"""
app/core/logging.py
──────────────────────────────────────────────────────────────────────────────
Structured logging setup using structlog.

Features:
  - JSON output in production, colourised console output in development.
  - `request_id` is automatically injected into every log call via context vars.
  - Standard library `logging` is bridged to structlog so third-party
    libraries (SQLAlchemy, uvicorn) also emit structured logs.

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)

    logger.info("supplier_created", supplier_id=str(supplier.id))
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from app.core.config import settings


def _drop_color_message_key(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Remove uvicorn's `color_message` key — it duplicates `event` in JSON."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog + stdlib logging bridge.
    Called once at application startup in `app/main.py`.
    """
    log_level = getattr(logging, settings.logging.LOG_LEVEL, logging.INFO)
    is_json = settings.logging.LOG_FORMAT == "json"

    # ── Shared processors (run for every log event) ───────────────────────────
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,  # Injects request_id etc.
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _drop_color_message_key,
    ]

    if is_json:
        # Production: JSON output
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: pretty coloured output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    # ── Root handler ──────────────────────────────────────────────────────────
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # ── Silence noisy libraries ───────────────────────────────────────────────
    for noisy in ("httpcore", "httpx", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    Return a bound structlog logger.

    Usage:
        logger = get_logger(__name__)
        logger.info("event_name", key="value")
    """
    return structlog.get_logger(name)
