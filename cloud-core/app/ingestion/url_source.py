"""
URL ingestion with SSRF controls (P12-07; ADR-072).

WHY THIS IS THE MOST DANGEROUS CODE IN THE INGESTION PATH

Every other input arrives as bytes the caller already had. A URL makes the
*server* issue a request, with the server's network position — inside the
VPC, able to reach the metadata service, able to reach internal admin
panels a user never could. A naive fetcher turns "ingest this article" into
a read primitive against the private network.

DEFENCE ORDER, AND WHY

    1. scheme allow-list        http/https only; file:// and gopher:// are
                                not "unusual", they are exfiltration
    2. resolve DNS ourselves    so we know the actual IP before connecting
    3. reject private targets   loopback, RFC1918, link-local, CGNAT, ULA,
                                and the cloud metadata addresses
    4. connect to the IP        with the Host header preserved, so the name
                                cannot resolve differently the second time
    5. re-validate each hop     a redirect is a fresh request to a fresh
                                address, and 302 -> 169.254.169.254 is the
                                classic bypass
    6. bound the response       size and time, enforced while streaming

Step 4 is what closes DNS rebinding. Validating a hostname and then letting
the HTTP client resolve it again leaves a window in which the answer can
change; pinning the connection to the IP we validated removes the window
rather than narrowing it.

NO CREDENTIALS ARE EVER SENT. The fetcher carries no cookies, no auth
header, and does not forward the caller's token.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, 8080, 8443}
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 15.0

# Content types we will convert. Anything else is refused rather than
# guessed at — a mislabelled binary handed to a parser is how parser bugs
# get reached.
ALLOWED_CONTENT_TYPES = {
    "text/html", "application/xhtml+xml", "text/plain", "text/markdown",
    "application/pdf", "text/csv", "application/json", "application/xml", "text/xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# Cloud metadata endpoints. These are plain IPs that look unremarkable and
# return credentials; naming them explicitly is worth more than trusting the
# private-range check alone to cover them.
METADATA_ADDRESSES = {
    "169.254.169.254",   # AWS / Azure / GCP / DigitalOcean
    "fd00:ec2::254",     # AWS IPv6
    "100.100.100.200",   # Alibaba Cloud
    "192.0.0.192",       # Oracle Cloud
}


class UrlRejected(Exception):
    """Refusal with a reason. The reason is safe to log and safe to show a
    caller: it names the policy, never the resolved internal address."""


@dataclass
class FetchedResource:
    url: str
    final_url: str
    content: bytes
    content_type: str
    status_code: int
    redirects: list[str] = field(default_factory=list)
    resolved_ip: str = ""


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Returns a rejection reason, or None if the address is acceptable.

    CHECK ORDER IS DELIBERATE: most specific first.

    Python's `is_private` is True for loopback, link-local AND unspecified
    addresses, so checking it early would label every one of them "private
    network address". They are all blocked either way, but an operator
    reading the audit log is better served by "cloud metadata endpoint" than
    by a generic reason - the two warrant very different reactions.
    """
    if str(ip) in METADATA_ADDRESSES:
        return "cloud metadata endpoint"

    # IPv4-mapped IPv6 (::ffff:127.0.0.1) smuggles a v4 target past a check
    # that only inspects v6 properties. Resolved BEFORE the generic checks
    # so the reported reason describes the real target.
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            inner = _is_forbidden_ip(mapped)
            if inner:
                return f"IPv4-mapped {inner}"

    if ip.is_unspecified:
        return "unspecified address"
    if ip.is_loopback:
        return "loopback address"
    if ip.is_link_local:
        return "link-local address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_private:
        return "private network address"
    if ip.is_reserved:
        return "reserved address"
    if isinstance(ip, ipaddress.IPv4Address):
        # 100.64.0.0/10 CGNAT: not "private" by Python's definition but
        # still carrier-internal and not a legitimate ingestion target.
        if ipaddress.IPv4Address("100.64.0.0") <= ip <= ipaddress.IPv4Address("100.127.255.255"):
            return "carrier-grade NAT address"
    elif ip.is_site_local:
        return "site-local address"
    return None


def validate_url(url: str) -> tuple[str, int, str]:
    """Structural validation. Returns (hostname, port, scheme).

    Raises `UrlRejected` before any network activity — a malformed or
    non-HTTP URL must never reach a socket."""
    if not url or len(url) > 2048:
        raise UrlRejected("URL is empty or exceeds 2048 characters")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UrlRejected(
            f"Scheme {parsed.scheme!r} is not permitted; only http and https are fetched"
        )
    if not parsed.hostname:
        raise UrlRejected("URL has no hostname")
    if parsed.username or parsed.password:
        # user:pass@host is a credential-leak vector and an easy way to
        # confuse host parsing.
        raise UrlRejected("URLs containing credentials are not accepted")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UrlRejected(f"Port {port} is not permitted")

    return parsed.hostname, port, parsed.scheme.lower()


def resolve_and_validate(hostname: str, port: int) -> str:
    """Resolves DNS and rejects any address pointing inside the network.

    EVERY resolved address is checked, not just the first: a hostname with
    both a public and a private A record would otherwise pass validation and
    then connect to the private one."""
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlRejected(f"Hostname could not be resolved: {exc.strerror or 'DNS failure'}") from None

    if not infos:
        raise UrlRejected("Hostname resolved to no addresses")

    resolved: list[str] = []
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise UrlRejected("Hostname resolved to an unparseable address") from None
        reason = _is_forbidden_ip(ip)
        if reason:
            # The reason names the POLICY, not the address - echoing the
            # resolved internal IP back to a caller is itself a small
            # disclosure.
            raise UrlRejected(f"Refusing to fetch: target resolves to a {reason}")
        resolved.append(address)

    return resolved[0]


def fetch_url(url: str, *, max_bytes: int = MAX_RESPONSE_BYTES) -> FetchedResource:
    """Fetches a URL with every hop validated.

    Redirects are followed manually rather than by the HTTP client, because
    automatic following would perform the request to the new location before
    we could inspect it — and `302 -> http://169.254.169.254/` is the single
    most common SSRF bypass.
    """
    import httpx

    seen: list[str] = []
    current = url

    for _ in range(MAX_REDIRECTS + 1):
        hostname, port, scheme = validate_url(current)
        ip = resolve_and_validate(hostname, port)

        parsed = urlparse(current)
        # Connect to the VALIDATED IP with the original Host header, so the
        # name cannot resolve to something else between check and connect.
        connect_netloc = f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
        pinned = urlunparse((scheme, connect_netloc, parsed.path or "/",
                             parsed.params, parsed.query, ""))

        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT,
                                      write=READ_TIMEOUT, pool=CONNECT_TIMEOUT),
                follow_redirects=False,
                verify=scheme == "https",
                # No cookies, no auth: nothing of the caller's is forwarded.
                headers={"Host": parsed.netloc, "User-Agent": "AIOL-Ingestion/1.0",
                         "Accept-Encoding": "identity"},
            ) as client:
                # The socket goes to the pinned IP, but TLS must be verified against the NAME: without
                # sni_hostname the certificate is checked against the IP and every real HTTPS site fails
                # with "IP address mismatch" (security audit 2026-10-14, finding SEC-01).
                ext = {"sni_hostname": hostname} if scheme == "https" else {}
                with client.stream("GET", pinned, extensions=ext) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise UrlRejected("Redirect response carried no Location header")
                        seen.append(current)
                        current = httpx.URL(current).join(location).__str__()
                        continue

                    if response.status_code >= 400:
                        raise UrlRejected(f"Upstream returned HTTP {response.status_code}")

                    content_type = (
                        response.headers.get("content-type", "").split(";")[0].strip().lower()
                    )
                    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                        raise UrlRejected(f"Content-Type {content_type!r} is not accepted")

                    # Declared length is a hint from an untrusted server; the
                    # real enforcement is while streaming.
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise UrlRejected(f"Response exceeds the {max_bytes} byte limit")

                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise UrlRejected(f"Response exceeds the {max_bytes} byte limit")
                        chunks.append(chunk)

                    return FetchedResource(
                        url=url, final_url=current, content=b"".join(chunks),
                        content_type=content_type or "application/octet-stream",
                        status_code=response.status_code, redirects=seen, resolved_ip=ip,
                    )
        except UrlRejected:
            raise
        except Exception as exc:
            raise UrlRejected(f"Fetch failed: {type(exc).__name__}") from None

    raise UrlRejected(f"Exceeded {MAX_REDIRECTS} redirects")


def filename_for(resource: FetchedResource) -> str:
    """A safe filename derived from content type, never from the URL path.

    Using the path would let a crafted URL choose an extension, which is the
    same class of problem as trusting an uploaded filename."""
    suffix = {
        "text/html": ".html", "application/xhtml+xml": ".html",
        "text/plain": ".txt", "text/markdown": ".md",
        "application/pdf": ".pdf", "text/csv": ".csv",
        "application/json": ".json", "application/xml": ".xml", "text/xml": ".xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    }.get(resource.content_type, ".bin")
    import hashlib

    return f"{hashlib.sha256(resource.final_url.encode()).hexdigest()[:16]}{suffix}"
