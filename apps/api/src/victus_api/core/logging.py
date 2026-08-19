"""Structured logging via structlog.

JSON output in non-development environments; ConsoleRenderer with colors in dev.
A `request_id` context variable is injected by middleware to thread one ID
across all logs emitted while serving a single HTTP request.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

from victus_api.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    request_id = request_id_var.get()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.api_log_level,
    )
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_request_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.api_env == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.api_log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def redact_phone(phone: str | None) -> str:
    """Mask a phone number for logs, keeping only the last three digits.

    The WhatsApp rail is the one place a direct identifier enters the system.
    The database is careful with it — ``User`` rows hold no phone at all and
    participants are reachable only through a pseudonymous session — but logs
    are a separate store with wider access, longer retention, and no erasure
    path: ``scrub_phone`` clears queued jobs, and cannot reach a line already
    flushed to stdout and shipped off the host.

    Three digits is enough to match a participant who is on the phone telling
    you their number, which is the only support workflow that needs it. The
    length is preserved so a malformed number still looks malformed in the logs.
    """
    if not phone:
        return "<none>"
    digits = phone.strip()
    if len(digits) <= 3:
        return "*" * len(digits)
    return "*" * (len(digits) - 3) + digits[-3:]
