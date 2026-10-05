"""HTTP middleware: request id, access log, security headers."""

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var

access_log = logging.getLogger("app.access")

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


DASHBOARD_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'none'"
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gives every request an id (reused from X-Request-ID if it looks safe), logs one line
    per request with status and duration, and adds security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            access_log.info(
                f"{request.method} {request.url.path} {status}",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else None,
                },
            )
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        path = request.url.path
        if path.startswith("/assets/") and status == 200:
            # Built files have a content hash in their name: they never change, cache for a year.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        if path.startswith("/api/"):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        elif not path.startswith(("/docs", "/redoc", "/openapi.json")):
            # Dashboard pages: only this site's own scripts and data. (MUI adds inline styles.)
            response.headers.setdefault("Content-Security-Policy", DASHBOARD_CSP)
        return response
