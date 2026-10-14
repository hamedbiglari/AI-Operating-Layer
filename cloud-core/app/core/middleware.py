"""
Request ID middleware.

Attaches a unique request_id to every incoming request so logs and error
responses can be correlated (API design principle, section 51: "request
IDs").

Phase 1 fix (per Phase 0 review): a client-supplied `X-Request-ID` is no
longer trusted blindly. It is validated for length and character set;
anything invalid is replaced with a freshly generated UUID instead of
being echoed back or logged verbatim.
"""

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("app.request")

# Conservative allow-list: hex UUID-like or short alphanumeric/dash/underscore
# tokens only. Anything else (excessive length, control characters, header
# injection attempts, etc.) is rejected and replaced.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _sanitize_request_id(raw: str | None) -> str:
    if raw and _REQUEST_ID_PATTERN.match(raw):
        return raw
    return str(uuid.uuid4())


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = _sanitize_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %s (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response
