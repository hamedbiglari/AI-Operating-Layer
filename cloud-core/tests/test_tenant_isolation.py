"""
THE GOLDEN TEST SUITE.

Per the Phase 0 review: a user from Organization A must never be able to
read, list, or otherwise learn about a resource belonging to Organization
B — not even via a 403 that would confirm the resource exists. Every
assertion below checks for 404 on cross-tenant access, and for the
resource never leaking into another organization's list results.

This is intentionally the most heavily tested behavior in Phase 1.
"""

from fastapi.testclient import TestClient


def test_user_cannot_read_another_organizations_site_by_id(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()

    site_b = client.post(
        "/api/v1/sites",
        json={"name": "B Site", "domain": "b-site.example.com"},
        headers=org_b["headers"],
    ).json()

    response = client.get(f"/api/v1/sites/{site_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_another_organizations_site(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()

    site_b = client.post(
        "/api/v1/sites",
        json={"name": "B Site", "domain": "b-site2.example.com"},
        headers=org_b["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/sites/{site_b['id']}",
        json={"name": "Hijacked"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_archive_another_organizations_site(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()

    site_b = client.post(
        "/api/v1/sites",
        json={"name": "B Site", "domain": "b-site3.example.com"},
        headers=org_b["headers"],
    ).json()

    response = client.delete(f"/api/v1/sites/{site_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_site_list_never_includes_other_organizations_sites(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()

    client.post(
        "/api/v1/sites",
        json={"name": "A Site", "domain": "a-only.example.com"},
        headers=org_a["headers"],
    )
    client.post(
        "/api/v1/sites",
        json={"name": "B Site", "domain": "b-only.example.com"},
        headers=org_b["headers"],
    )

    response = client.get("/api/v1/sites", headers=org_a["headers"])
    assert response.status_code == 200
    domains = [site["domain"] for site in response.json()["items"]]
    assert "a-only.example.com" in domains
    assert "b-only.example.com" not in domains


def test_user_cannot_read_another_organizations_user_by_id(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()

    response = client.get(f"/api/v1/users/{org_b['user']['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_list_never_includes_other_organizations_users(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()

    response = client.get("/api/v1/users", headers=org_a["headers"])
    assert response.status_code == 200
    user_ids = [u["id"] for u in response.json()["items"]]
    assert org_a["user"]["id"] in user_ids
    assert org_b["user"]["id"] not in user_ids


def test_organizations_me_always_resolves_to_callers_own_organization(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()

    response_a = client.get("/api/v1/organizations/me", headers=org_a["headers"])
    response_b = client.get("/api/v1/organizations/me", headers=org_b["headers"])

    assert response_a.json()["id"] == org_a["organization"]["id"]
    assert response_b.json()["id"] == org_b["organization"]["id"]
    assert response_a.json()["id"] != response_b.json()["id"]


def test_token_forged_with_foreign_organization_id_still_cannot_read_that_org(
    client: TestClient, register_org
) -> None:
    """Even if a caller somehow obtained a syntactically valid token
    claiming a foreign organization_id, `get_current_user` re-derives the
    organization from the user row in the database — it never trusts the
    token's `org` claim for authorization decisions on its own."""
    from tests.conftest import bearer_header  # local import to avoid unused-import lint noise

    org_a = register_org()
    org_b = register_org()

    forged_headers = bearer_header(
        user_id=org_a["user"]["id"],
        organization_id=org_b["organization"]["id"],  # forged claim
        role="owner",
    )

    response = client.get("/api/v1/organizations/me", headers=forged_headers)
    assert response.status_code == 200
    # Must resolve to A's real organization (from the DB), never B's.
    assert response.json()["id"] == org_a["organization"]["id"]
