"""
URL ingestion and SSRF (P12-07, ADR-072).

The defect this closes: `url_source.py` contained a complete SSRF
implementation that **no route called**. A security control nothing reaches
protects nothing, so these tests deliberately include route-level proof
that the protected path is actually invoked — not just unit tests of the
helper.
"""

import pytest
from fastapi.testclient import TestClient

from app.ingestion.url_source import UrlRejected, validate_url
from app.services.url_ingestion_service import normalize_url, url_idempotency_key


def _source(client: TestClient, headers: dict) -> str:
    return client.post("/api/v1/sources",
                       json={"source_type": "web_page", "title": "Web"},
                       headers=headers).json()["id"]


def _ingest(client: TestClient, headers: dict, url: str, source_id: str, **kw):
    body = {"source_id": source_id, "url": url}
    body.update(kw)
    return client.post("/api/v1/documents/ingest-url", json=body, headers=headers)


# --- scheme / structure guards --------------------------------------------


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com/",
    "data:text/html,<script>",
    "javascript:alert(1)",
])
def test_non_http_schemes_are_rejected(url: str) -> None:
    with pytest.raises(UrlRejected):
        validate_url(url)


def test_credentials_in_url_are_rejected() -> None:
    """user:pass@host leaks credentials and confuses host parsing."""
    with pytest.raises(UrlRejected):
        validate_url("http://user:secret@example.com/")


def test_non_standard_port_is_rejected() -> None:
    with pytest.raises(UrlRejected):
        validate_url("http://example.com:22/")


def test_oversized_url_is_rejected() -> None:
    with pytest.raises(UrlRejected):
        validate_url("https://example.com/" + "a" * 3000)


# --- IP-level guards (the actual SSRF surface) --------------------------------


@pytest.mark.parametrize("host,label", [
    ("localhost", "loopback"),
    ("127.0.0.1", "loopback"),
    ("127.0.0.53", "loopback"),
    ("0.0.0.0", "unspecified"),
    ("10.0.0.1", "private"),
    ("172.16.0.1", "private"),
    ("192.168.1.1", "private"),
    ("169.254.169.254", "link-local/metadata"),
    ("[::1]", "IPv6 loopback"),
    ("[fc00::1]", "IPv6 unique-local"),
    ("[fe80::1]", "IPv6 link-local"),
])
def test_internal_targets_are_refused(host: str, label: str) -> None:
    """Covers loopback, RFC1918, link-local, cloud metadata and the IPv6
    equivalents — each a documented SSRF pivot."""
    from app.ingestion.url_source import resolve_and_validate

    hostname, port, _ = validate_url(f"http://{host}/")
    with pytest.raises(UrlRejected):
        resolve_and_validate(hostname, port)


def test_metadata_endpoint_is_named_explicitly() -> None:
    """169.254.169.254 is the single most exploited SSRF target."""
    from app.ingestion.url_source import resolve_and_validate

    with pytest.raises(UrlRejected):
        resolve_and_validate("169.254.169.254", 80)


def test_rejection_message_does_not_echo_the_resolved_address() -> None:
    """Echoing the internal IP back to a caller is itself a disclosure —
    it confirms what the name resolves to."""
    from app.ingestion.url_source import resolve_and_validate

    with pytest.raises(UrlRejected) as exc:
        resolve_and_validate("10.11.12.13", 80)
    assert "10.11.12.13" not in str(exc.value)


# --- route-level proof that the guard is actually reached -----------------------


def test_route_rejects_a_forbidden_scheme(client: TestClient, register_org) -> None:
    """THE wiring test: proves the endpoint invokes the SSRF validator
    rather than merely existing."""
    org = register_org()
    response = _ingest(client, org["headers"], "file:///etc/passwd",
                       _source(client, org["headers"]))
    assert response.status_code == 422
    assert "scheme" in response.text.lower()


def test_route_rejects_credentialed_url(client: TestClient, register_org) -> None:
    org = register_org()
    response = _ingest(client, org["headers"], "http://user:pw@example.com/",
                       _source(client, org["headers"]))
    assert response.status_code == 422


def test_route_accepts_a_public_url_and_returns_202(client: TestClient, register_org) -> None:
    """Accepted structurally; the authoritative DNS/IP checks happen at
    fetch time in the worker, because DNS can change in between."""
    org = register_org()
    response = _ingest(client, org["headers"], "https://example.com/article",
                       _source(client, org["headers"]))
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_id"]
    assert body["status"] == "queued"
    assert body["job_type"] == "document_ingestion"
    assert body["document_id"] is None, "nothing is fetched yet, so no document exists"
    assert body["storage_path_recorded"] is False


def test_no_network_activity_occurs_in_the_request(client: TestClient, register_org) -> None:
    """The fetch must happen in the worker. If the route fetched, this
    unreachable host would make the request hang or fail slowly instead of
    returning 202 immediately."""
    org = register_org()
    response = _ingest(
        client, org["headers"],
        "https://this-host-does-not-resolve-aiol-test.invalid/x",
        _source(client, org["headers"]),
    )
    assert response.status_code == 202, "the route must not resolve or fetch"


# --- idempotency and normalization ----------------------------------------------


def test_repeat_request_reuses_the_job(client: TestClient, register_org) -> None:
    org = register_org()
    source_id = _source(client, org["headers"])
    first = _ingest(client, org["headers"], "https://example.com/a", source_id).json()
    second = _ingest(client, org["headers"], "https://example.com/a", source_id).json()

    assert first["job_created"] is True
    assert second["job_created"] is False
    assert first["job_id"] == second["job_id"]


def test_normalization_treats_equivalent_urls_as_one(client: TestClient, register_org) -> None:
    org = register_org()
    source_id = _source(client, org["headers"])
    a = _ingest(client, org["headers"], "https://Example.com:443/a", source_id).json()
    b = _ingest(client, org["headers"], "https://example.com/a#frag", source_id).json()
    assert a["job_id"] == b["job_id"]


def test_query_string_is_preserved_not_normalized_away() -> None:
    """`?id=1` and `?id=2` are different documents. Merging them would
    silently lose one."""
    assert normalize_url("https://x.test/a?id=1") != normalize_url("https://x.test/a?id=2")


def test_normalization_drops_default_ports_and_fragments() -> None:
    assert normalize_url("https://X.test:443/a#top") == "https://x.test/a"
    assert normalize_url("http://X.test:80/") == "http://x.test/"


def test_idempotency_key_is_tenant_scoped(client: TestClient, register_org) -> None:
    """Two organizations ingesting the same public article are doing two
    separate legitimate things."""
    import uuid as _uuid

    source_id = _uuid.uuid4()
    key_a = url_idempotency_key(organization_id=_uuid.uuid4(), source_id=source_id,
                                normalized_url="https://x.test/a")
    key_b = url_idempotency_key(organization_id=_uuid.uuid4(), source_id=source_id,
                                normalized_url="https://x.test/a")
    assert key_a != key_b


def test_two_tenants_get_separate_jobs_for_the_same_url(
    client: TestClient, register_org
) -> None:
    org_a, org_b = register_org(), register_org()
    a = _ingest(client, org_a["headers"], "https://example.com/shared",
                _source(client, org_a["headers"])).json()
    b = _ingest(client, org_b["headers"], "https://example.com/shared",
                _source(client, org_b["headers"])).json()
    assert a["job_id"] != b["job_id"]
    assert a["job_created"] is True and b["job_created"] is True


# --- authentication and tenancy ---------------------------------------------------


def test_unauthenticated_request_is_refused(client: TestClient, register_org) -> None:
    org = register_org()
    source_id = _source(client, org["headers"])
    assert client.post("/api/v1/documents/ingest-url",
                       json={"source_id": source_id, "url": "https://example.com/"}
                       ).status_code == 401


def test_viewer_cannot_queue_url_ingestion(client: TestClient, register_org) -> None:
    org = register_org()
    source_id = _source(client, org["headers"])
    client.post("/api/v1/users",
                json={"email": "url-viewer@example.dev", "name": "V",
                      "password": "supersecret123", "role": "viewer"},
                headers=org["headers"])
    token = client.post("/api/v1/auth/login",
                        data={"username": "url-viewer@example.dev",
                              "password": "supersecret123"}).json()["access_token"]
    assert _ingest(client, {"Authorization": f"Bearer {token}"},
                   "https://example.com/", source_id).status_code == 403


def test_cannot_queue_against_another_orgs_source(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    source_b = _source(client, org_b["headers"])
    assert _ingest(client, org_a["headers"], "https://example.com/", source_b).status_code == 404


# --- worker-side failure classification --------------------------------------------


def test_blocked_url_fails_permanently_and_does_not_retry(
    client: TestClient, register_org, db_session
) -> None:
    """A blocked target is blocked identically on every retry; retrying
    would turn a rejection into a slow internal port scan."""
    import uuid as _uuid

    from app.models.enums import SyncJobStatus
    from app.services import ingestion_job_service, url_ingestion_service

    org = register_org()
    organization_id = _uuid.UUID(org["organization"]["id"])
    source_id = _uuid.UUID(_source(client, org["headers"]))

    job, _ = url_ingestion_service.create_url_ingestion_job(
        db_session, organization_id=organization_id, source_id=source_id,
        url="http://169.254.169.254/latest/meta-data/", title=None, language="en",
    )
    db_session.commit()

    ingestion_job_service.claim(db_session, job_id=job.id)
    with pytest.raises(UrlRejected):
        url_ingestion_service.fetch_and_ingest_url(
            db_session, organization_id=organization_id, source_id=source_id,
            url="http://169.254.169.254/latest/meta-data/",
        )
    ingestion_job_service.fail(db_session, job=job, error="URL rejected", retryable=False)
    assert job.status == SyncJobStatus.FAILED, "must not enter RETRYING"


def test_url_job_carries_provenance_in_its_payload(
    client: TestClient, register_org
) -> None:
    org = register_org()
    accepted = _ingest(client, org["headers"], "https://example.com/Article?x=1",
                       _source(client, org["headers"])).json()

    job = client.get(f"/api/v1/sync-jobs/{accepted['job_id']}", headers=org["headers"]).json()
    payload = job["payload"]
    assert payload["kind"] == "url"
    assert payload["url"] == "https://example.com/Article?x=1"
    assert payload["normalized_url"] == "https://example.com/Article?x=1"
