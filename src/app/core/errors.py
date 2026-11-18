import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


class ServiceError(Exception):
    status_code = 500
    code = "service_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnauthorizedError(ServiceError):
    status_code = 401
    code = "unauthorized"


class RateLimitError(ServiceError):
    status_code = 429
    code = "rate_limited"


class NotFoundError(ServiceError):
    status_code = 404
    code = "not_found"


class InvalidDocumentError(ServiceError):
    status_code = 422
    code = "invalid_document"


class ProviderError(ServiceError):
    status_code = 502
    code = "provider_error"


class TransientProviderError(ProviderError):
    """A provider timeout or server failure that may be retried or failed over."""


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        logger.warning("request_failed", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
