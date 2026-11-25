"""Application exceptions and consistent HTTP error response handlers."""

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Base exception carrying a safe API error code and client message."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        """Initialize an application error for the API response."""
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UnauthorizedError(AppError):
    """Raised when a request does not contain a valid bearer token."""

    def __init__(self) -> None:
        """Initialize a generic authorization error without token details."""
        super().__init__("UNAUTHORIZED", "Valid bearer token required", 401)


class ServiceConfigurationError(AppError):
    """Raised when runtime credentials required by a service are unavailable."""

    def __init__(self) -> None:
        """Initialize a safe configuration error without exposing key material."""
        super().__init__("SERVICE_CONFIGURATION_ERROR", "Service is not configured", 500)


class LLMProviderError(AppError):
    """Raised when an upstream LLM provider call fails or times out."""

    def __init__(self, message: str = "Upstream LLM request failed") -> None:
        """Initialize a safe provider error without exposing internal payloads."""
        super().__init__("LLM_PROVIDER_ERROR", message, 502)


def _request_id(request: Request) -> str:
    """Read the request ID assigned by middleware, with a safe fallback."""
    return str(getattr(request.state, "request_id", "unknown"))


def _error_response(
    request: Request,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    """Build the standard JSON error envelope."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": _request_id(request),
            }
        },
        headers={"X-Request-ID": _request_id(request)},
    )


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """Convert a typed application error into the standard response envelope."""
    return _error_response(request, exc.code, exc.message, exc.status_code)


async def handle_http_error(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Convert framework HTTP errors without returning internal detail."""
    message = str(exc.detail) if isinstance(exc.detail, str) else "Request failed"
    return _error_response(request, "HTTP_ERROR", message, exc.status_code)


async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return a stable validation error without echoing submitted values."""
    return _error_response(request, "VALIDATION_ERROR", "Request validation failed", 422)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log an unexpected server failure and return a non-sensitive error."""
    logger.error(
        "unhandled_exception",
        request_id=_request_id(request),
        exception_type=type(exc).__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(request, "INTERNAL_SERVER_ERROR", "An unexpected error occurred", 500)


def register_exception_handlers(app: FastAPI) -> None:
    """Register consistent handlers for application and framework errors."""
    app.add_exception_handler(AppError, handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, handle_http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, handle_unexpected_error)
