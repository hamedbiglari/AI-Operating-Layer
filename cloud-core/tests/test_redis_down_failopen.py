"""
Redis-down / fail-open behaviour (ADR-039).

The rate limiter is deliberately fail-open: if Redis is unreachable the
request proceeds rather than 503-ing, because a cache outage turning
into a total integration outage is the worse failure.

That is only an acceptable trade-off if the things fail-open must NOT
weaken are actually still enforced. This file tests that claim instead
of asserting it:

    Redis DOWN
        -> rate limiting unavailable
        -> request may proceed
        BUT
        -> authentication still mandatory
        -> tenant still derived from the credential, never the request
        -> authorization (scopes) still enforced
        -> the limiter failure is logged

Redis failure is simulated two ways, because they fail at different
points and only testing one would leave a gap:
  1. the client cannot be constructed at all (`_redis_client` -> None)
  2. the client exists but every command raises (a live-but-broken
     Redis, which is the more realistic outage)
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app.security import rate_limit


class _BrokenRedis:
    """A client that connects but whose commands fail — models a Redis
    that is up but unhealthy, which `_redis_client() -> None` does
    not."""

    def incr(self, *a, **kw):
        raise ConnectionError("simulated redis failure")

    def expire(self, *a, **kw):
        raise ConnectionError("simulated redis failure")

    def ttl(self, *a, **kw):
        raise ConnectionError("simulated redis failure")


@pytest.fixture()
def redis_unavailable(monkeypatch):
    """Case 1: the limiter cannot get a client at all."""
    monkeypatch.setattr(rate_limit, "_redis_client", lambda: None)


@pytest.fixture()
def redis_broken(monkeypatch):
    """Case 2: the limiter gets a client, and every command raises."""
    monkeypatch.setattr(rate_limit, "_redis_client", lambda: _BrokenRedis())


def _site(client: TestClient, headers: dict, domain: str) -> dict:
    return client.post(
        "/api/v1/sites", json={"name": "Store", "domain": domain}, headers=headers
    ).json()


def _installation(client: TestClient, headers: dict, site_id: str | None = None) -> dict:
    payload = {"name": "WP", "adapter_type": "wordpress"}
    if site_id:
        payload["site_id"] = site_id
    return client.post("/api/v1/installations", json=payload, headers=headers).json()


def _token(client: TestClient, headers: dict, installation_id: str, scopes=None) -> str:
    return client.post(
        f"/api/v1/installations/{installation_id}/credentials",
        json={"scopes": scopes or ["mappings:read", "mappings:write"]},
        headers=headers,
    ).json()["token"]


def _machine(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _knowledge(client: TestClient, headers: dict) -> dict:
    return client.post(
        "/api/v1/knowledge", json={"canonical_name": "K", "object_type": "plant"}, headers=headers
    ).json()


# --- 1. Fail-open: the request proceeds ------------------------------------


def test_request_proceeds_when_redis_client_unavailable(
    client: TestClient, register_org, redis_unavailable
) -> None:
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    token = _token(client, org["headers"], inst["id"])
    ko = _knowledge(client, org["headers"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": 1},
        headers=_machine(token),
    )
    assert response.status_code == 200, response.text


def test_request_proceeds_when_redis_commands_raise(
    client: TestClient, register_org, redis_broken
) -> None:
    """The more realistic outage: Redis is up but every command fails."""
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    token = _token(client, org["headers"], inst["id"])
    ko = _knowledge(client, org["headers"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": 2},
        headers=_machine(token),
    )
    assert response.status_code == 200, response.text


def test_no_429_is_ever_returned_while_redis_is_down(
    client: TestClient, register_org, redis_broken
) -> None:
    """Far more requests than the configured limit (120) would normally
    allow — none may be throttled, since there is no counter."""
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    token = _token(client, org["headers"], inst["id"])

    statuses = {
        client.get("/api/v1/adapter/mappings", headers=_machine(token)).status_code
        for _ in range(30)
    }
    assert statuses == {200}


# --- 2. Authentication is STILL mandatory ----------------------------------


def test_authentication_still_required_when_redis_is_down(
    client: TestClient, register_org, redis_broken
) -> None:
    """Fail-open applies to the LIMITER only. It must not become
    fail-open authentication."""
    for headers in ({}, _machine("garbage"), {"Authorization": "Basic x"}):
        assert client.get("/api/v1/adapter/mappings", headers=headers).status_code == 401


def test_revoked_credential_still_rejected_when_redis_is_down(
    client: TestClient, register_org, redis_broken
) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    body = client.post(
        f"/api/v1/installations/{inst['id']}/credentials",
        json={"scopes": ["mappings:read"]}, headers=org["headers"],
    ).json()
    client.post(f"/api/v1/credentials/{body['credential']['id']}/revoke", headers=org["headers"])

    assert client.get(
        "/api/v1/adapter/mappings", headers=_machine(body["token"])
    ).status_code == 401


# --- 3. Tenant derivation/isolation is STILL enforced -------------------------


def test_tenant_still_derived_from_credential_when_redis_is_down(
    client: TestClient, register_org, redis_broken
) -> None:
    """A forged organization_id in the body must still be ignored."""
    org_a, org_b = register_org(), register_org()
    site_a = _site(client, org_a["headers"], "a.example")
    inst_a = _installation(client, org_a["headers"], site_a["id"])
    token_a = _token(client, org_a["headers"], inst_a["id"])
    ko_a = _knowledge(client, org_a["headers"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={
            "object_type": "knowledge_object", "object_id": ko_a["id"], "wordpress_post_id": 3,
            "organization_id": org_b["organization"]["id"],  # forged
        },
        headers=_machine(token_a),
    )
    assert response.status_code == 200
    assert response.json()["mapping"]["organization_id"] == org_a["organization"]["id"]


def test_cross_tenant_object_still_rejected_when_redis_is_down(
    client: TestClient, register_org, redis_broken
) -> None:
    org_a, org_b = register_org(), register_org()
    site_a = _site(client, org_a["headers"], "a.example")
    inst_a = _installation(client, org_a["headers"], site_a["id"])
    token_a = _token(client, org_a["headers"], inst_a["id"])
    ko_b = _knowledge(client, org_b["headers"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko_b["id"], "wordpress_post_id": 4},
        headers=_machine(token_a),
    )
    assert response.status_code == 404


def test_mapping_list_still_tenant_scoped_when_redis_is_down(
    client: TestClient, register_org, redis_broken
) -> None:
    org_a, org_b = register_org(), register_org()
    for org, domain, post_id in ((org_a, "a.example", 11), (org_b, "b.example", 22)):
        site = _site(client, org["headers"], domain)
        inst = _installation(client, org["headers"], site["id"])
        tok = _token(client, org["headers"], inst["id"])
        ko = _knowledge(client, org["headers"])
        client.post(
            "/api/v1/adapter/mappings",
            json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": post_id},
            headers=_machine(tok),
        )
        if org is org_a:
            token_a = tok

    listing = client.get("/api/v1/adapter/mappings", headers=_machine(token_a)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["wordpress_post_id"] == 11


# --- 4. Authorization (scopes) is STILL enforced --------------------------------


def test_scope_still_enforced_when_redis_is_down(
    client: TestClient, register_org, redis_broken
) -> None:
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    read_only = _token(client, org["headers"], inst["id"], scopes=["mappings:read"])
    ko = _knowledge(client, org["headers"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": 5},
        headers=_machine(read_only),
    )
    assert response.status_code == 403


# --- 5. The limiter failure is observable -----------------------------------------


def test_limiter_failure_is_logged(caplog, redis_broken) -> None:
    """Called directly: a silent fail-open would be the dangerous kind,
    because an operator would never learn the limiter had stopped
    working."""
    with caplog.at_level(logging.WARNING, logger="app.security.rate_limit"):
        result = rate_limit.check_rate_limit(installation_id="abc", limit=5)

    assert result.allowed is True
    assert any("Rate limiter unavailable" in r.message for r in caplog.records)


def test_missing_client_path_allows_without_crashing(redis_unavailable) -> None:
    result = rate_limit.check_rate_limit(installation_id="abc", limit=5)
    assert result.allowed is True
    assert result.remaining == result.limit


def test_readiness_reports_redis_but_stays_ready(client: TestClient, monkeypatch) -> None:
    """Redis degradation must be VISIBLE but must not fail readiness —
    the app still serves correctly without a limiter."""
    from app.api.v1 import health

    monkeypatch.setattr(health, "_redis_status", lambda: "degraded: ConnectionError")
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["redis"].startswith("degraded")
