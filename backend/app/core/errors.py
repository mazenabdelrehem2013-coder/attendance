"""One error format for every failure:

    {"error": {"code": "NOT_FOUND", "message": "...", "request_id": "...", "details": [...]}}

Unexpected errors are logged in full on the server but the client only sees a generic message,
so internal details (SQL, file paths, stack traces) never leak to phones or browsers.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    503: "SERVICE_UNAVAILABLE",
}


class AppError(Exception):
    """Raise this from services for expected business errors."""

    def __init__(self, status_code: int, code: str, message: str, headers: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def _body(request: Request, code: str, message: str, details: list | None = None) -> dict:
    error = {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}
    if details:
        error["details"] = details
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(
            _body(request, exc.code, exc.message), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else code
        return JSONResponse(
            _body(request, code, message),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        # Report which field is wrong and why, but never echo the submitted values back.
        if any(err.get("type") == "json_invalid" for err in exc.errors()):
            return JSONResponse(
                _body(
                    request,
                    "INVALID_JSON",
                    "The request is not valid JSON. Check the quotes, commas and braces, "
                    'and write a backslash as "\\\\".',
                ),
                status_code=422,
            )
        details = [
            {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "issue": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            _body(request, "VALIDATION_ERROR", "Some fields are missing or invalid.", details),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            _body(request, "INTERNAL_ERROR", "Something went wrong. Please try again later."),
            status_code=500,
        )
