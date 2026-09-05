"""Map domain errors onto the API contract's error envelope (API.md)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import AppError

log = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable]
):
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def _envelope(
    code: str, message: str, retryable: bool, request_id: str | None, status: int
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "request_id": request_id,
            }
        },
        headers={REQUEST_ID_HEADER: request_id} if request_id else None,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return _envelope(
            exc.code,
            exc.message,
            exc.retryable,
            getattr(request.state, "request_id", None),
            exc.http_status,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return _envelope(
            "INVALID_SCRIPT",
            "The request payload is invalid.",
            False,
            getattr(request.state, "request_id", None),
            422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        return _envelope(
            "NOT_FOUND" if exc.status_code == 404 else "REQUEST_FAILED",
            str(exc.detail),
            False,
            getattr(request.state, "request_id", None),
            exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Log the detail, return none of it: provider errors can carry keys.
        log.exception("Unhandled error", exc_info=exc)
        return _envelope(
            "INTERNAL_ERROR",
            "An unexpected error occurred.",
            False,
            getattr(request.state, "request_id", None),
            500,
        )
