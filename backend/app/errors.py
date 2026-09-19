"""Consistent API error envelope.

Every error response looks like:

    {"error": {"code": "SESSION_NOT_FOUND", "message": "..."}}

Routers/services raise ``APIError`` with a stable machine code + HTTP status.
Plain ``HTTPException`` and validation errors are also wrapped so the frontend
never has to special-case shapes. Internal details (SQL, stack traces, keys)
are never leaked — unexpected 500s return a generic message.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("heard.errors")


class APIError(Exception):
    """Raise for any expected, client-facing error."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


# Map bare HTTP status codes to stable string codes for HTTPException fallbacks.
_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError):
        return _envelope(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code, "ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _envelope(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        # Surface a compact hint without leaking the whole pydantic tree.
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        msg = first.get("msg", "Invalid request.")
        message = f"{loc}: {msg}" if loc else msg
        return _envelope(422, "VALIDATION_ERROR", message)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        logger.exception("unhandled error: %s", exc)
        return _envelope(500, "INTERNAL_ERROR", "An unexpected error occurred.")
