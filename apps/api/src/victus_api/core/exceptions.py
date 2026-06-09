"""Domain exceptions and FastAPI handlers.

Internal errors retain full stack traces in the structured log while
returning a stable, user-safe error code + message to the client.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from sqlalchemy.exc import IntegrityError

from victus_api.core.logging import get_logger

log = get_logger(__name__)


class VictusError(Exception):
    """Base class for application-level errors with a stable error code."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "victus_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(VictusError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_failed"


class InvalidCredentialsError(AuthenticationError):
    error_code = "invalid_credentials"


class TokenExpiredError(AuthenticationError):
    error_code = "token_expired"


class TokenInvalidError(AuthenticationError):
    error_code = "token_invalid"


class AuthorizationError(VictusError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"


class ConsentRequiredError(AuthorizationError):
    error_code = "consent_required"


class NotFoundError(VictusError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ConflictError(VictusError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


class EmailAlreadyRegisteredError(ConflictError):
    error_code = "email_already_registered"


def _error_response(
    error_code: str,
    message: str,
    *,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> ORJSONResponse:
    body: dict[str, Any] = {"error": {"code": error_code, "message": message}}
    if details:
        body["error"]["details"] = details
    return ORJSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VictusError)
    async def _victus_handler(_: Request, exc: VictusError) -> ORJSONResponse:
        log.warning(
            "victus_error",
            error_code=exc.error_code,
            status_code=exc.status_code,
            message=exc.message,
        )
        return _error_response(
            exc.error_code,
            exc.message,
            status_code=exc.status_code,
            details=exc.details or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> ORJSONResponse:
        return _error_response(
            "validation_error",
            "Request payload failed validation.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"errors": exc.errors()},
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_handler(_: Request, exc: IntegrityError) -> ORJSONResponse:
        log.warning("db_integrity_error", error=str(exc.orig))
        return _error_response(
            "conflict",
            "A database constraint was violated.",
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> ORJSONResponse:
        log.exception("unhandled_exception", exception_type=type(exc).__name__)
        return _error_response(
            "internal_server_error",
            "An unexpected error occurred. Please try again later.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
