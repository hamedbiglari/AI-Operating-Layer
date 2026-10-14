"""
Integration tests for user management and role-based authorization.
"""

from fastapi.testclient import TestClient


def test_owner_can_create_teammate(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/users",
        json={
            "email": "teammate@example.dev",
            "name": "Teammate",
            "password": "supersecret123",
            "role": "editor",
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "teammate@example.dev"
    assert body["role"] == "editor"
    assert body["organization_id"] == org["organization"]["id"]


def test_duplicate_email_within_same_org_conflicts(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={
            "email": "same@example.dev",
            "name": "First",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    )
    response = client.post(
        "/api/v1/users",
        json={
            "email": "same@example.dev",
            "name": "Second",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    )
    assert response.status_code == 409


def test_viewer_cannot_create_user(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={
            "email": "viewer@example.dev",
            "name": "Viewer",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/users",
        json={
            "email": "another@example.dev",
            "name": "Another",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_any_authenticated_user_can_read_their_own_user_record(
    client: TestClient, register_org
) -> None:
    org = register_org()
    response = client.get(f"/api/v1/users/{org['user']['id']}", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["id"] == org["user"]["id"]


def test_unknown_user_id_returns_404(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000000", headers=org["headers"]
    )
    assert response.status_code == 404


def test_owner_can_update_teammate_role(client: TestClient, register_org) -> None:
    org = register_org()
    teammate = client.post(
        "/api/v1/users",
        json={
            "email": "promote-me@example.dev",
            "name": "Future Admin",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/users/{teammate['id']}",
        json={"role": "admin"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_list_users_is_paginated(client: TestClient, register_org) -> None:
    org = register_org()
    for i in range(3):
        client.post(
            "/api/v1/users",
            json={
                "email": f"page{i}@example.dev",
                "name": f"Page {i}",
                "password": "supersecret123",
                "role": "viewer",
            },
            headers=org["headers"],
        )

    response = client.get("/api/v1/users?limit=2&offset=0", headers=org["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    assert body["total"] >= 4  # owner + 3 teammates
