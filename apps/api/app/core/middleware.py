import logging
import re
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import error_response

logger = logging.getLogger("vantage.http")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", "")
        if not REQUEST_ID_PATTERN.fullmatch(request_id):
            request_id = str(uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        content_length = request.headers.get("content-length", "")
        if content_length.isdecimal() and int(content_length) > get_settings().request_body_limit_bytes:
            response = error_response(request, 413, "payload_too_large", "Request body exceeds the configured limit")
        else:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.error(
                    "Unhandled request error",
                    extra={"request_id": request_id, "error_type": type(exc).__name__},
                )
                response = error_response(request, 500, "internal_error", "An internal error occurred")
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        logger.info(
            "HTTP request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
