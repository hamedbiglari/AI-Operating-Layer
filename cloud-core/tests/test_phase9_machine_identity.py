"""
Adversarial tests for machine identity, rate limiting and the adapter
boundary (Phase 9).

The security property under test throughout: **tenant is derived from
the credential, never from the request.**
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _site(client: TestClient, headers: dict, domain: str) -> dict:
    return client.post(
        "/api/v1/sites", json={"name": "Store", "domain": domain}, headers=headers
    ).json()


def _installation(client: TestClient, headers: dict, site_id: str | None = None) -> dict:
    payload = {"name": "WP Install", "adapter_type": "wordpress"}
    if site_id:
        payload["site_id"] = site_id
    return client.post("/api/v1/installations", json=payload, headers=headers).json()


def _credential(client: TestClient, headers: dict, installation_id: str, scopes=None) -> tuple[dict, str]:
    body = client.post(
        f"/api/v1/installations/{installation_id}/credentials",
        json={"scopes": scopes or ["mappings:read", "mappings:write"]},
        headers=headers,
    ).json()
    return body["credential"], body["token"]


def _machine(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _knowledge(client: TestClient, headers: dict, name: str = "Taranjabin") -> dict:
    return client.post(
        "/api/v1/knowledge", json={"canonical_name": name, "object_type": "plant"}, headers=headers
    ).json()


# --- Authentication ---------------------------------------------------------


def test_valid_credential_resolves_to_its_own_organization(client: TestClient, register_org) -> None:
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    _, token = _credential(client, org["headers"], inst["id"])

    response = client.get("/api/v1/adapter/identity", headers=_machine(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization_id"] == org["organization"]["id"]
    assert body["installation_id"] == inst["id"]


def test_secret_is_returned_once_and_never_again(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    credential, token = _credential(client, org["headers"], inst["id"])
    assert token

    listing = client.get(
        f"/api/v1/installations/{inst['id']}/credentials", headers=org["headers"]
    ).json()
    stored = listing["items"][0]
    assert "secret" not in stored
    assert "token" not in stored
    assert "secret_hash" not in stored
    assert stored["key_id"] == credential["key_id"]
    assert token not in str(stored)


def test_garbage_and_missing_tokens_are_rejected(client: TestClient, register_org) -> None:
    for headers in ({}, _machine("garbage"), _machine("aiol_only_two"), {"Authorization": "Basic x"}):
        assert client.get("/api/v1/adapter/identity", headers=headers).status_code == 401


def test_wrong_secret_for_a_real_key_id_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    credential, _ = _credential(client, org["headers"], inst["id"])

    forged = f"aiol_{credential['key_id']}_wrongsecretwrongsecret"
    assert client.get("/api/v1/adapter/identity", headers=_machine(forged)).status_code == 401


def test_user_jwt_cannot_authenticate_as_a_machine(client: TestClient, register_org) -> None:
    """The two realms are separate — a human token is not an adapter."""
    org = register_org()
    user_token = org["headers"]["Authorization"].split()[1]
    assert client.get("/api/v1/adapter/identity", headers=_machine(user_token)).status_code == 401


def test_revoked_credential_stops_working_immediately(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    credential, token = _credential(client, org["headers"], inst["id"])
    assert client.get("/api/v1/adapter/identity", headers=_machine(token)).status_code == 200

    client.post(f"/api/v1/credentials/{credential['id']}/revoke", headers=org["headers"])
    assert client.get("/api/v1/adapter/identity", headers=_machine(token)).status_code == 401


def test_suspended_installation_blocks_its_credentials(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    _, token = _credential(client, org["headers"], inst["id"])

    client.post(f"/api/v1/installations/{inst['id']}/status", json={"status": "suspended"}, headers=org["headers"])
    assert client.get("/api/v1/adapter/identity", headers=_machine(token)).status_code == 401


def test_revoked_installation_cannot_be_reactivated(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    client.post(f"/api/v1/installations/{inst['id']}/status", json={"status": "revoked"}, headers=org["headers"])

    response = client.post(
        f"/api/v1/installations/{inst['id']}/status", json={"status": "active"}, headers=org["headers"]
    )
    assert response.status_code == 422


def test_rotation_issues_a_new_token_and_retires_the_old(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    credential, old_token = _credential(client, org["headers"], inst["id"])

    rotated = client.post(f"/api/v1/credentials/{credential['id']}/rotate", headers=org["headers"]).json()
    new_token = rotated["token"]
    assert new_token != old_token

    assert client.get("/api/v1/adapter/identity", headers=_machine(old_token)).status_code == 401
    assert client.get("/api/v1/adapter/identity", headers=_machine(new_token)).status_code == 200


def test_expired_credential_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    body = client.post(
        f"/api/v1/installations/{inst['id']}/credentials",
        json={"scopes": ["mappings:read"], "expires_at": past},
        headers=org["headers"],
    ).json()
    assert client.get("/api/v1/adapter/identity", headers=_machine(body["token"])).status_code == 401


# --- Authorization (scopes) ---------------------------------------------------


def test_credential_without_write_scope_cannot_write_mappings(client: TestClient, register_org) -> None:
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    _, token = _credential(client, org["headers"], inst["id"], scopes=["mappings:read"])
    ko = _knowledge(client, org["headers"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": 10},
        headers=_machine(token),
    )
    assert response.status_code == 403


# --- Tenant isolation: the central case -----------------------------------------


def test_adapter_cannot_map_another_orgs_object(client: TestClient, register_org) -> None:
    """Tenant A's installation naming Tenant B's knowledge object."""
    org_a, org_b = register_org(), register_org()
    site_a = _site(client, org_a["headers"], "a.example")
    inst_a = _installation(client, org_a["headers"], site_a["id"])
    _, token_a = _credential(client, org_a["headers"], inst_a["id"])
    ko_b = _knowledge(client, org_b["headers"], "B Object")

    response = client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko_b["id"], "wordpress_post_id": 10},
        headers=_machine(token_a),
    )
    assert response.status_code == 404


def test_client_supplied_organization_id_is_ignored(client: TestClient, register_org) -> None:
    """An adapter that puts someone else's organization_id in the body
    must not be believed — the field does not participate in
    authentication and is not part of the contract."""
    org_a, org_b = register_org(), register_org()
    site_a = _site(client, org_a["headers"], "a.example")
    inst_a = _installation(client, org_a["headers"], site_a["id"])
    _, token_a = _credential(client, org_a["headers"], inst_a["id"])
    ko_a = _knowledge(client, org_a["headers"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={
            "object_type": "knowledge_object", "object_id": ko_a["id"], "wordpress_post_id": 10,
            "organization_id": org_b["organization"]["id"],  # forged, must be ignored
            "site_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=_machine(token_a),
    )
    assert response.status_code == 200
    assert response.json()["mapping"]["organization_id"] == org_a["organization"]["id"]
    assert response.json()["mapping"]["site_id"] == site_a["id"]


def test_adapter_mapping_list_never_shows_another_orgs_mappings(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    for org, domain, post_id in ((org_a, "a.example", 11), (org_b, "b.example", 22)):
        site = _site(client, org["headers"], domain)
        inst = _installation(client, org["headers"], site["id"])
        _, token = _credential(client, org["headers"], inst["id"])
        ko = _knowledge(client, org["headers"])
        client.post(
            "/api/v1/adapter/mappings",
            json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": post_id},
            headers=_machine(token),
        )
        if org is org_a:
            token_a = token

    listing = client.get("/api/v1/adapter/mappings", headers=_machine(token_a)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["wordpress_post_id"] == 11


def test_user_cannot_see_another_orgs_installations(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    inst_b = _installation(client, org_b["headers"])
    assert client.get(f"/api/v1/installations/{inst_b['id']}", headers=org_a["headers"]).status_code == 404


def test_user_cannot_revoke_another_orgs_credential(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    inst_b = _installation(client, org_b["headers"])
    credential_b, _ = _credential(client, org_b["headers"], inst_b["id"])
    response = client.post(f"/api/v1/credentials/{credential_b['id']}/revoke", headers=org_a["headers"])
    assert response.status_code == 404


# --- Idempotency ------------------------------------------------------------------


def test_same_event_delivered_five_times_creates_one_mapping(client: TestClient, register_org) -> None:
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    _, token = _credential(client, org["headers"], inst["id"])
    ko = _knowledge(client, org["headers"])
    payload = {"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": 42}

    results = [
        client.post("/api/v1/adapter/mappings", json=payload, headers=_machine(token)).json()
        for _ in range(5)
    ]
    assert results[0]["created"] is True
    assert all(r["created"] is False for r in results[1:])
    assert len({r["mapping"]["id"] for r in results}) == 1

    listing = client.get("/api/v1/adapter/mappings", headers=_machine(token)).json()
    assert listing["total"] == 1


def test_remapping_an_object_to_a_different_post_is_a_conflict_not_a_silent_overwrite(
    client: TestClient, register_org
) -> None:
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    _, token = _credential(client, org["headers"], inst["id"])
    ko = _knowledge(client, org["headers"])
    client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": 42},
        headers=_machine(token),
    )

    response = client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": 99},
        headers=_machine(token),
    )
    assert response.status_code == 409


def test_unknown_object_id_fails_safely(client: TestClient, register_org) -> None:
    org = register_org()
    site = _site(client, org["headers"], "a.example")
    inst = _installation(client, org["headers"], site["id"])
    _, token = _credential(client, org["headers"], inst["id"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={
            "object_type": "product",
            "object_id": "00000000-0000-0000-0000-000000000000",
            "wordpress_post_id": 7,
        },
        headers=_machine(token),
    )
    assert response.status_code == 404
    assert "Traceback" not in response.text
    assert "SELECT" not in response.text


def test_installation_without_a_site_cannot_map(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])  # no site
    _, token = _credential(client, org["headers"], inst["id"])
    ko = _knowledge(client, org["headers"])

    response = client.post(
        "/api/v1/adapter/mappings",
        json={"object_type": "knowledge_object", "object_id": ko["id"], "wordpress_post_id": 1},
        headers=_machine(token),
    )
    assert response.status_code == 422


# --- Adapter cannot reach Core decisions -------------------------------------------


def test_adapter_has_no_scope_that_can_verify_evidence_or_publish(client: TestClient, register_org) -> None:
    """The adapter boundary: no credential scope exists that grants
    evidence verification, trust verification, or product publication.
    Those are Core decisions."""
    from app.models.enums import AdapterScope

    granted = {s.value for s in AdapterScope}
    for forbidden in ("evidence:verify", "trust:verify", "products:publish", "recommendations:write"):
        assert forbidden not in granted


def test_adapter_credential_cannot_call_human_endpoints(client: TestClient, register_org) -> None:
    org = register_org()
    inst = _installation(client, org["headers"])
    _, token = _credential(client, org["headers"], inst["id"])

    # A machine token is not a user token: human-realm routes reject it.
    for path in ("/api/v1/products", "/api/v1/installations", "/api/v1/recommendations"):
        assert client.get(path, headers=_machine(token)).status_code == 401
