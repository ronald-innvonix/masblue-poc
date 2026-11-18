import logging
import re
import time
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog
from fastapi import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_PII_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
    re.IGNORECASE,
)
logger = structlog.get_logger(__name__)


def redact_pii(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key, value in tuple(event_dict.items()):
        if isinstance(value, str) and key not in {"event", "logger", "level"}:
            event_dict[key] = _PII_PATTERN.sub("[REDACTED]", value)
    return event_dict


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_pii,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def bind_request_id(request: Request, call_next: Any) -> Any:
    started = time.monotonic()
    candidate = request.headers.get("X-Request-ID", "")
    request_id = (
        candidate if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", candidate) else str(uuid.uuid4())
    )
    token = request_id_var.set(request_id)
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            method=request.method,
            status_code=response.status_code,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return response
    finally:
        structlog.contextvars.clear_contextvars()
        request_id_var.reset(token)
