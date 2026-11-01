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


import re  # noqa: E402

import pytest  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services import email_delivery  # noqa: E402


@pytest.fixture()
def outbox(monkeypatch):
    """Delivery replaced by a capturing function here only (as in test_login_code.py)."""
    sent = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.invalid")
    monkeypatch.setattr(email_delivery, "send", lambda **kw: sent.append(kw))
    return sent


def _viewer(client: TestClient, register_org, email: str = "viewer-self@example.dev") -> tuple[dict, dict]:
    org = register_org()
    viewer = {"email": email, "name": "Viewer", "password": "supersecret123", "role": "viewer"}
    assert client.post("/api/v1/users", json=viewer, headers=org["headers"]).status_code == 201
    token = client.post("/api/v1/auth/login", data={"username": viewer["email"], "password": viewer["password"]}).json()["access_token"]
    return org, {"Authorization": f"Bearer {token}"}


def test_user_edits_own_profile(client: TestClient, register_org) -> None:
    """V5-settings-self-profile: PATCH /users/me changes only the caller's own name; never the sign-in email."""
    _, h = _viewer(client, register_org)
    r = client.patch("/api/v1/users/me", json={"name": "Viewer Renamed"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Viewer Renamed" and r.json()["role"] == "viewer"
    assert client.get("/api/v1/auth/me", headers=h).json()["user"]["name"] == "Viewer Renamed"
    # Only the name: a role in the body is ignored, never applied.
    r = client.patch("/api/v1/users/me", json={"role": "owner"}, headers=h)
    assert r.status_code == 200 and r.json()["role"] == "viewer"
    # The sign-in email cannot be changed here (V5-self-email-verification): 422, and nothing changes.
    r = client.patch("/api/v1/users/me", json={"name": "X", "email": "new@example.dev"}, headers=h)
    assert r.status_code == 422
    me = client.get("/api/v1/auth/me", headers=h).json()["user"]
    assert me["email"] == "viewer-self@example.dev" and me["name"] == "Viewer Renamed"
    # Invalid input.
    assert client.patch("/api/v1/users/me", json={"name": ""}, headers=h).status_code == 422
    assert client.patch("/api/v1/users/me", json={"name": "   "}, headers=h).status_code == 422
    assert client.patch("/api/v1/users/me", json={"name": "x"}).status_code == 401


REQ, VER = "/api/v1/users/me/email-change-request", "/api/v1/users/me/email-change-verify"


def _code(outbox) -> str:
    return re.search(r"\b(\d{6})\b", outbox[-1]["body"]).group(1)


def test_email_change_needs_the_code_sent_to_the_new_address(client: TestClient, register_org, outbox) -> None:
    """V5-self-email-verification: request -> code to the NEW address -> verify; only then the email changes."""
    _, h = _viewer(client, register_org)
    r = client.post(REQ, json={"new_email": "Viewer.New@Example.dev"}, headers=h)
    assert r.status_code == 202, r.text
    assert r.json()["sent_to"] == "viewer.new@example.dev"
    assert len(outbox) == 1 and outbox[0]["to"] == "viewer.new@example.dev"
    code = _code(outbox)
    # Nothing has changed yet.
    assert client.get("/api/v1/auth/me", headers=h).json()["user"]["email"] == "viewer-self@example.dev"
    # A wrong code is refused and changes nothing.
    wrong = "000000" if code != "000000" else "111111"
    assert client.post(VER, json={"code": wrong}, headers=h).status_code == 400
    assert client.post(VER, json={"code": "12ab56"}, headers=h).status_code == 422
    # The right code applies the change; the old address is told.
    r = client.post(VER, json={"code": code}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "viewer.new@example.dev"
    assert client.get("/api/v1/auth/me", headers=h).json()["user"]["email"] == "viewer.new@example.dev"
    assert outbox[-1]["to"] == "viewer-self@example.dev" and "changed" in outbox[-1]["subject"]
    # The code is single-use; signing in uses the new address.
    assert client.post(VER, json={"code": code}, headers=h).status_code == 404
    assert client.post("/api/v1/auth/login", data={"username": "viewer.new@example.dev", "password": "supersecret123"}).status_code == 200


def test_email_change_refusals(client: TestClient, register_org, outbox, monkeypatch) -> None:
    org, h = _viewer(client, register_org, "viewer-refuse@example.dev")
    other_email = client.get("/api/v1/auth/me", headers=org["headers"]).json()["user"]["email"]
    # Taken address (409), own address (422), not an address (422): nothing is sent.
    assert client.post(REQ, json={"new_email": other_email.upper()}, headers=h).status_code == 409
    assert client.post(REQ, json={"new_email": "viewer-refuse@example.dev"}, headers=h).status_code == 422
    assert client.post(REQ, json={"new_email": "not-an-email"}, headers=h).status_code == 422
    assert outbox == []
    # No pending request: verify answers 404.
    assert client.post(VER, json={"code": "123456"}, headers=h).status_code == 404
    # The same address again inside the resend window: 429 with Retry-After.
    assert client.post(REQ, json={"new_email": "a1@example.dev"}, headers=h).status_code == 202
    r = client.post(REQ, json={"new_email": "a1@example.dev"}, headers=h)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    # A different address supersedes the earlier request: the first code no longer works.
    first = _code(outbox)
    assert client.post(REQ, json={"new_email": "a2@example.dev"}, headers=h).status_code == 202
    second = _code(outbox)
    if first != second:
        assert client.post(VER, json={"code": first}, headers=h).status_code == 400
    # Three wrong codes void the request.
    bad = "000000" if second != "000000" else "111111"
    for _ in range(settings.LOGIN_CODE_MAX_FAILURES - 1 - (1 if first != second else 0)):
        assert client.post(VER, json={"code": bad}, headers=h).status_code == 400
    assert client.post(VER, json={"code": bad}, headers=h).status_code == 429
    assert client.post(VER, json={"code": second}, headers=h).status_code == 404
    assert client.get("/api/v1/auth/me", headers=h).json()["user"]["email"] == "viewer-refuse@example.dev"
    # The address taken by someone else between request and verify: 409 at verify, nothing changes.
    assert client.post(REQ, json={"new_email": "race@example.dev"}, headers=h).status_code == 202
    code = _code(outbox)
    assert client.post("/api/v1/users", json={"email": "race@example.dev", "name": "R", "password": "supersecret123",
                                              "role": "viewer"}, headers=org["headers"]).status_code == 201
    assert client.post(VER, json={"code": code}, headers=h).status_code == 409
    assert client.get("/api/v1/auth/me", headers=h).json()["user"]["email"] == "viewer-refuse@example.dev"
    # Without SMTP nothing is created and the caller is told (503).
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    assert client.post(REQ, json={"new_email": "nosmtp@example.dev"}, headers=h).status_code == 503
    # Auth required.
    assert client.post(REQ, json={"new_email": "x@example.dev"}).status_code == 401
