"""
URL ingestion SSRF controls (P12-07, ADR-072).

A URL makes the SERVER issue a request, from the server's network position.
These tests assert refusal for every class of target that turns "ingest this
article" into a read primitive against the private network.
"""

import ipaddress

import pytest

from app.ingestion.url_source import (
    ALLOWED_SCHEMES,
    METADATA_ADDRESSES,
    UrlRejected,
    _is_forbidden_ip,
    filename_for,
    resolve_and_validate,
    validate_url,
)


def _reject(url: str) -> str:
    with pytest.raises(UrlRejected) as exc:
        hostname, port, _ = validate_url(url)
        resolve_and_validate(hostname, port)
    return str(exc.value)


# --- scheme and structure ---------------------------------------------------


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "gopher://internal/_",
    "ftp://internal/x",
    "dict://localhost:11211/",
    "jar:http://x/!/",
])
def test_non_http_schemes_are_refused(url: str) -> None:
    """file:// and gopher:// are not unusual — they are exfiltration."""
    assert "not permitted" in _reject(url)


def test_credentials_in_url_are_refused() -> None:
    assert "credentials" in _reject("http://user:pass@example.com/")


@pytest.mark.parametrize("port", [22, 25, 3306, 5432, 6379, 11211])
def test_non_web_ports_are_refused(port: int) -> None:
    assert "Port" in _reject(f"http://example.com:{port}/")


def test_oversized_url_is_refused() -> None:
    assert _reject("https://example.com/" + "a" * 2100)


def test_only_http_and_https_are_allowed() -> None:
    assert ALLOWED_SCHEMES == {"http", "https"}


# --- private and internal targets ---------------------------------------------


@pytest.mark.parametrize("url,expected", [
    ("http://localhost/x", "loopback"),
    ("http://127.0.0.1/x", "loopback"),
    ("http://127.1.2.3/x", "loopback"),
    ("http://[::1]/x", "loopback"),
    ("http://10.0.0.1/x", "private"),
    ("http://172.16.0.1/x", "private"),
    ("http://192.168.1.1/x", "private"),
    ("http://169.254.1.1/x", "link-local"),
    ("http://0.0.0.0/x", "unspecified"),
])
def test_private_targets_are_refused(url: str, expected: str) -> None:
    assert expected in _reject(url)


@pytest.mark.parametrize("address", sorted(METADATA_ADDRESSES))
def test_cloud_metadata_endpoints_are_refused(address: str) -> None:
    """These return credentials and look unremarkable. Naming them
    explicitly is worth more than trusting a range check to cover them."""
    reason = _is_forbidden_ip(ipaddress.ip_address(address))
    assert reason is not None


def test_metadata_address_is_refused_through_the_url_path() -> None:
    assert "metadata" in _reject("http://169.254.169.254/latest/meta-data/iam/")


def test_carrier_grade_nat_is_refused() -> None:
    assert _is_forbidden_ip(ipaddress.ip_address("100.64.0.1")) is not None


def test_ipv4_mapped_ipv6_cannot_smuggle_a_loopback_target() -> None:
    """`::ffff:127.0.0.1` slips past a check that only looks at v6
    properties."""
    reason = _is_forbidden_ip(ipaddress.ip_address("::ffff:127.0.0.1"))
    assert reason is not None and "loopback" in reason


def test_ipv6_unique_local_is_refused() -> None:
    assert _is_forbidden_ip(ipaddress.ip_address("fd00::1")) is not None


def test_public_address_is_permitted() -> None:
    """The control must not be so broad it blocks legitimate ingestion."""
    assert _is_forbidden_ip(ipaddress.ip_address("93.184.216.34")) is None
    assert _is_forbidden_ip(ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946")) is None


# --- rejection messages must not disclose internals -------------------------------


def test_rejection_names_the_policy_not_the_resolved_address() -> None:
    """Echoing the resolved internal IP back to a caller is itself a small
    disclosure — it confirms what the name resolves to inside the network."""
    message = _reject("http://10.0.0.1/x")
    assert "private network address" in message
    assert "10.0.0.1" not in message


# --- filename derivation ------------------------------------------------------------


def test_filename_comes_from_content_type_not_the_url_path() -> None:
    """Using the path would let a crafted URL choose its own extension —
    the same problem as trusting an uploaded filename."""
    from app.ingestion.url_source import FetchedResource

    resource = FetchedResource(
        url="http://x.test/evil.php", final_url="http://x.test/evil.php",
        content=b"<html></html>", content_type="text/html", status_code=200,
    )
    name = filename_for(resource)
    assert name.endswith(".html")
    assert "evil" not in name
    assert ".php" not in name


def test_unknown_content_type_gets_an_inert_suffix() -> None:
    from app.ingestion.url_source import FetchedResource

    resource = FetchedResource(
        url="http://x.test/a", final_url="http://x.test/a", content=b"",
        content_type="application/x-sh", status_code=200,
    )
    assert filename_for(resource).endswith(".bin")


# --- structural guarantees ----------------------------------------------------------


def test_redirects_are_followed_manually_not_by_the_client() -> None:
    """Automatic redirect following performs the request to the new location
    before it can be inspected — `302 -> 169.254.169.254` is the classic
    bypass. The client must be configured not to follow."""
    import inspect

    from app.ingestion import url_source

    source = inspect.getsource(url_source.fetch_url)
    assert "follow_redirects=False" in source
    assert "MAX_REDIRECTS" in source


def test_connection_is_pinned_to_the_validated_ip() -> None:
    """Validating a hostname then letting the client re-resolve leaves a
    DNS-rebinding window. Connecting to the checked IP removes it."""
    import inspect

    from app.ingestion import url_source

    source = inspect.getsource(url_source.fetch_url)
    assert "resolve_and_validate" in source
    assert "connect_netloc" in source


def test_every_resolved_address_is_checked_not_only_the_first() -> None:
    """A hostname with both a public and a private A record would otherwise
    pass validation and then connect to the private one."""
    import inspect

    from app.ingestion import url_source

    source = inspect.getsource(url_source.resolve_and_validate)
    assert "for info in infos" in source


def test_no_caller_credentials_are_forwarded() -> None:
    """Asserts on EXECUTABLE code, not comments.

    The first version failed because the word "cookies" appears in a comment
    explaining that none are sent — the same weak-test shape that has bitten
    this project before (a guard whose own docstring trips it)."""
    import inspect
    import io
    import tokenize

    from app.ingestion import url_source

    raw = inspect.getsource(url_source.fetch_url)
    code = "".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(raw).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    assert "Authorization" not in code
    assert "cookies" not in code
    assert "auth=" not in code
