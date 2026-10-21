"""
GET /auth/network-check — advisory VPN / proxy signal for the login and sign-up pages.

It NEVER blocks sign-in or sign-up; it only lets the page recommend disconnecting a VPN/proxy.
What can honestly be detected without an external service is limited to proxy headers the
connection itself carries (Via, Forwarded / X-Forwarded-For beyond our own trusted hops,
well-known proxy headers). Consumer VPNs usually add no header: detecting them needs an
IP-reputation service, which is not configured -> reported as `ip_reputation: not_configured`.
The response never echoes the client's IP address or header values.
"""
from fastapi import APIRouter, HTTPException, Request, status

from app.security.client_ip import client_ip
from app.core.config import settings
from app.security.rate_limit import check_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])
KNOWN_PROXY_HEADERS = ("x-proxy-id", "proxy-connection", "x-bluecoat-via", "x-proxyuser-ip", "client-ip", "x-real-forwarded-for")


def _signals(request: Request) -> list[str]:
    h = request.headers
    out = []
    if h.get("via"):
        out.append("via_header")
    hops = 0
    if h.get("x-forwarded-for"):
        hops = max(hops, len([x for x in h["x-forwarded-for"].split(",") if x.strip()]))
    if h.get("forwarded"):
        hops = max(hops, h["forwarded"].lower().count("for="))
    if hops > settings.TRUSTED_PROXY_HOPS:
        out.append("forwarded_chain")
    if any(h.get(k) for k in KNOWN_PROXY_HEADERS):
        out.append("proxy_header")
    return out


@router.get("/network-check")
def network_check(request: Request) -> dict:
    ip = client_ip(request)
    rl = check_rate_limit(installation_id=f"network-check:{ip}", limit=60)
    if not rl.allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many checks.", headers={"Retry-After": str(rl.retry_after)})
    signals = _signals(request)
    return {
        "suspected": bool(signals),
        "signals": signals,
        "ip_reputation": "not_configured",
        "blocking": False,
        "advice": ("It looks like you're using a VPN or proxy. For the most reliable sign-in and sign-up we recommend "
                   "disconnecting it — you can still continue.") if signals else None,
        "limits": "Only proxy headers are checked; VPNs that add no header are not detectable without an IP-reputation service.",
    }
