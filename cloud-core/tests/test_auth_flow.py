"""
Integration tests for the registration/login/me flow. Requires a real
Postgres connection (see tests/conftest.py `db_engine`).
"""

from fastapi.testclient import TestClient


def test_register_organization_creates_org_and_owner(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Acme Herbs",
            "owner_email": "owner@acme.dev",
            "owner_name": "Ada Owner",
            "owner_password": "supersecret123",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["organization"]["slug"] == "acme-herbs"
    assert body["organization"]["status"] == "active"
    assert body["user"]["role"] == "owner"
    assert body["user"]["email"] == "owner@acme.dev"
    assert body["token"]["access_token"]
    assert body["token"]["token_type"] == "bearer"


def test_register_duplicate_email_returns_409(client: TestClient) -> None:
    payload = {
        "organization_name": "Org One",
        "owner_email": "dup@acme.dev",
        "owner_name": "Owner",
        "owner_password": "supersecret123",
    }
    first = client.post("/api/v1/auth/register-organization", json=payload)
    assert first.status_code == 201

    second_payload = {**payload, "organization_name": "Org Two"}
    second = client.post("/api/v1/auth/register-organization", json=second_payload)
    assert second.status_code == 409


def test_first_organization_still_created_after_duplicate_attempt(client: TestClient) -> None:
    """Regression guard: a failed duplicate-email registration must not
    have left a half-created organization from ITS OWN attempt, and must
    not corrupt the earlier, successful organization."""
    payload = {
        "organization_name": "Org One",
        "owner_email": "dup2@acme.dev",
        "owner_name": "Owner",
        "owner_password": "supersecret123",
    }
    client.post("/api/v1/auth/register-organization", json=payload)
    client.post(
        "/api/v1/auth/register-organization",
        json={**payload, "organization_name": "Org Two"},
    )

    login = client.post(
        "/api/v1/auth/login",
        data={"username": "dup2@acme.dev", "password": "supersecret123"},
    )
    assert login.status_code == 200


def test_login_success(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Login Org",
            "owner_email": "login@acme.dev",
            "owner_name": "Owner",
            "owner_password": "supersecret123",
        },
    )
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "login@acme.dev", "password": "supersecret123"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Login Org 2",
            "owner_email": "login2@acme.dev",
            "owner_name": "Owner",
            "owner_password": "supersecret123",
        },
    )
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "login2@acme.dev", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_login_unknown_email_returns_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@nowhere.dev", "password": "whatever123"},
    )
    assert response.status_code == 401


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user_and_organization(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.get("/api/v1/auth/me", headers=org["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == org["user"]["id"]
    assert body["organization"]["id"] == org["organization"]["id"]


def test_me_rejects_garbage_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
