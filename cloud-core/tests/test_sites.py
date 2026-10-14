"""
Integration tests for site management.
"""

from fastapi.testclient import TestClient


def test_admin_can_create_site(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/sites",
        json={
            "name": "Main Site",
            "domain": "main.example.com",
            "platform": "wordpress",
            "woo_enabled": True,
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["domain"] == "main.example.com"
    assert body["status"] == "active"
    assert body["woo_enabled"] is True


def test_duplicate_domain_within_same_org_conflicts(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/sites",
        json={"name": "Site 1", "domain": "dup.example.com"},
        headers=org["headers"],
    )
    response = client.post(
        "/api/v1/sites",
        json={"name": "Site 2", "domain": "dup.example.com"},
        headers=org["headers"],
    )
    assert response.status_code == 409


def test_same_domain_allowed_across_different_organizations(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()

    resp_a = client.post(
        "/api/v1/sites",
        json={"name": "Shared Domain Site", "domain": "shared.example.com"},
        headers=org_a["headers"],
    )
    resp_b = client.post(
        "/api/v1/sites",
        json={"name": "Shared Domain Site", "domain": "shared.example.com"},
        headers=org_b["headers"],
    )
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201


def test_viewer_cannot_create_site(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={
            "email": "site-viewer@example.dev",
            "name": "Viewer",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "site-viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/sites",
        json={"name": "Should Fail", "domain": "should-fail.example.com"},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_archiving_site_soft_deletes_not_removes(client: TestClient, register_org) -> None:
    org = register_org()
    site = client.post(
        "/api/v1/sites",
        json={"name": "To Archive", "domain": "archive-me.example.com"},
        headers=org["headers"],
    ).json()

    archive_response = client.delete(f"/api/v1/sites/{site['id']}", headers=org["headers"])
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"

    # The row still exists and is still readable — this is a soft
    # delete, per master spec section 8.
    get_response = client.get(f"/api/v1/sites/{site['id']}", headers=org["headers"])
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "archived"


def test_update_site_fields(client: TestClient, register_org) -> None:
    org = register_org()
    site = client.post(
        "/api/v1/sites",
        json={"name": "Old Name", "domain": "update-me.example.com"},
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/sites/{site['id']}",
        json={"name": "New Name", "woo_enabled": True},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New Name"
    assert body["woo_enabled"] is True
