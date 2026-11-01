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


def test_user_edits_own_profile(client: TestClient, register_org) -> None:
    """V5-settings-self-profile: PATCH /users/me changes only the caller's own name and email."""
    org, other = register_org(), register_org()
    viewer = {"email": "viewer-self@example.dev", "name": "Viewer", "password": "supersecret123", "role": "viewer"}
    assert client.post("/api/v1/users", json=viewer, headers=org["headers"]).status_code == 201
    token = client.post("/api/v1/auth/login", data={"username": viewer["email"], "password": viewer["password"]}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # A viewer may edit their own profile (no admin role needed); email is stored lower-case.
    r = client.patch("/api/v1/users/me", json={"name": "Viewer Renamed", "email": "Viewer.New@Example.dev"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Viewer Renamed" and r.json()["email"] == "viewer.new@example.dev"
    assert r.json()["role"] == "viewer"
    me = client.get("/api/v1/auth/me", headers=h).json()["user"]
    assert me["name"] == "Viewer Renamed" and me["email"] == "viewer.new@example.dev"

    # Only name and email: a role in the body is ignored, never applied.
    r = client.patch("/api/v1/users/me", json={"role": "owner"}, headers=h)
    assert r.status_code == 200 and r.json()["role"] == "viewer"

    # An address already used anywhere on the platform is refused; nothing changes.
    other_email = client.get("/api/v1/auth/me", headers=other["headers"]).json()["user"]["email"]
    r = client.patch("/api/v1/users/me", json={"email": other_email}, headers=h)
    assert r.status_code == 409
    assert client.get("/api/v1/auth/me", headers=h).json()["user"]["email"] == "viewer.new@example.dev"

    # Invalid input.
    assert client.patch("/api/v1/users/me", json={"email": "not-an-email"}, headers=h).status_code == 422
    assert client.patch("/api/v1/users/me", json={"name": ""}, headers=h).status_code == 422
    assert client.patch("/api/v1/users/me", json={"name": "   "}, headers=h).status_code == 422
    assert client.patch("/api/v1/users/me", json={"name": "x"}).status_code == 401
