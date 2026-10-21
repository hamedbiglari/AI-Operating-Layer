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
_SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-site"),
)
# Responses that carry tokens or one-time codes must never sit in a shared or browser cache.
_NO_STORE_PREFIXES = ("/api/v1/auth/",)

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
        # Baseline hardening for every API response (security audit SEC-07). setdefault: a route that sets its
        # own value (e.g. a sandboxed HTML rendering) keeps it.
        for name, value in _SECURITY_HEADERS:
            response.headers.setdefault(name, value)
        if request.url.path.startswith(_NO_STORE_PREFIXES):
            response.headers["Cache-Control"] = "no-store"
        logger.info(
            "%s %s -> %s (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response


class BodySizeLimitMiddleware:
    """Refuses request bodies above a fixed size before they are read (security audit SEC-16).

    Without it a multipart upload is written to a temporary file in full before the endpoint's own size check
    runs, so one client could fill the disk. A declared Content-Length over the limit gets 413 at once; a
    chunked body is cut off as soon as it crosses the limit. Pure ASGI, so streaming responses are untouched.
    """

    def __init__(self, app, max_bytes: int) -> None:  # noqa: ANN001
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, send) -> None:  # noqa: ANN001
        body = b'{"error":{"code":"payload_too_large","message":"Request body is too large."}}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):  # noqa: ANN001
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        return await self._reject(send)
                except ValueError:
                    return await self._reject(send)
        from starlette.exceptions import HTTPException

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status_code=413, detail="Request body is too large.")
            return message

        return await self.app(scope, limited_receive, send)
