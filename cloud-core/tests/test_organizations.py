"""
Integration tests for the organization "me" endpoints.
"""

from fastapi.testclient import TestClient


def test_read_my_organization(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.get("/api/v1/organizations/me", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["id"] == org["organization"]["id"]


def test_owner_can_update_organization_name(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.patch(
        "/api/v1/organizations/me",
        json={"name": "Renamed Org"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Org"


def test_viewer_cannot_update_organization(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={
            "email": "org-viewer@example.dev",
            "name": "Viewer",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "org-viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.patch(
        "/api/v1/organizations/me",
        json={"name": "Should Not Change"},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_unauthenticated_request_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/organizations/me")
    assert response.status_code == 401
