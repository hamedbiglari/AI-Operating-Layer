"""The address a request really came from (security audit 2026-10-14, SEC-04).

Behind a reverse proxy or load balancer `request.client.host` is the proxy, so every per-IP rate limit
(login codes, sign-up, newsletter, network check) would count all visitors as one: one abuser could lock
everybody out. With `TRUSTED_PROXY_HOPS = N` (the number of proxies WE operate, each appending to
X-Forwarded-For) the client is the N-th entry from the right — entries further left were written by the
client itself and are never trusted. With N = 0 (default) the header is ignored entirely.
"""
from __future__ import annotations

import ipaddress

from starlette.requests import Request

from app.core.config import settings


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    hops = settings.TRUSTED_PROXY_HOPS
    if hops <= 0:
        return peer
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if len(parts) < hops:
        return peer          # header shorter than our own chain: not written by our proxies, ignore it
    candidate = parts[-hops]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return peer
