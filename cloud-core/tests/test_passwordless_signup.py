"""Passwordless organization sign-up (ADR-106)."""
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.models.signup_code import SignupCode
from app.services import email_delivery, signup_code_service

REQ = "/api/v1/auth/signup/request"
VER = "/api/v1/auth/signup/verify"


@pytest.fixture()
def mailbox(monkeypatch):
    sent = []
    monkeypatch.setattr(email_delivery, "is_configured", lambda: True)
    monkeypatch.setattr(email_delivery, "send", lambda **kw: sent.append(kw))
    monkeypatch.setattr(signup_code_service.email_delivery, "is_configured", lambda: True)
    monkeypatch.setattr(signup_code_service.email_delivery, "send", lambda **kw: sent.append(kw))
    return sent


def _email():
    return f"owner{uuid.uuid4().hex[:8]}@example.com"


def _code(sent):
    return re.search(r"\b(\d{6})\b", sent[-1]["body"]).group(1)


def _request(client, email, name="Toranjebin Co", owner="Marzieh"):
    return client.post(REQ, json={"organization_name": name, "owner_email": email, "owner_name": owner})


# ---------------------------------------------------------------- happy path
def test_signup_without_a_password(client: TestClient, mailbox, db_session) -> None:
    email = _email()
    r = _request(client, email)
    assert r.status_code == 202 and r.json()["status"] == "code_sent"
    v = client.post(VER, json={"owner_email": email, "code": _code(mailbox)})
    assert v.status_code == 201, v.text
    body = v.json()
    assert body["user"]["email"] == email and body["user"]["role"] == "owner" and body["token"]["access_token"]
    assert "password" not in v.text.lower()
    h = {"Authorization": f"Bearer {body['token']['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["organization"]["id"] == body["organization"]["id"]
    # the owner has no password at all, and password login cannot be used
    assert db_session.execute(text("SELECT password_hash FROM users WHERE email = :e"), {"e": email}).scalar_one() is None
    assert client.post("/api/v1/auth/login", data={"username": email, "password": "anything-at-all"}).status_code == 401
    assert db_session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'organization.registered' "
                                   "AND organization_id = :o"), {"o": body["organization"]["id"]}).scalar_one() == 1


def test_the_code_is_never_stored_or_returned_in_clear(client: TestClient, mailbox, db_session) -> None:
    email = _email()
    r = _request(client, email)
    code = _code(mailbox)
    assert code not in r.text
    row = db_session.execute(select(SignupCode).where(SignupCode.email == email)).scalar_one()
    assert row.code_hash != code and len(row.code_hash) == 64 and code not in row.code_hash


# ---------------------------------------------------------------- code rules
def test_wrong_code_then_lockout(client: TestClient, mailbox) -> None:
    email = _email()
    _request(client, email)
    good = _code(mailbox)
    bad = f"{(int(good) + 1) % 1000000:06d}"
    for _ in range(signup_code_service.MAX_ATTEMPTS):
        assert client.post(VER, json={"owner_email": email, "code": bad}).status_code == 401
    r = client.post(VER, json={"owner_email": email, "code": good})      # correct code, but the request is burnt
    assert r.status_code == 429 and "Too many" in r.text


def test_expired_code(client: TestClient, mailbox, db_session) -> None:
    email = _email()
    _request(client, email)
    db_session.execute(text("UPDATE signup_codes SET expires_at = :t WHERE email = :e"),
                       {"t": datetime.now(timezone.utc) - timedelta(seconds=1), "e": email})
    db_session.flush()
    r = client.post(VER, json={"owner_email": email, "code": _code(mailbox)})
    assert r.status_code == 410 and "expired" in r.text


def test_a_code_works_only_once(client: TestClient, mailbox) -> None:
    email = _email()
    _request(client, email)
    code = _code(mailbox)
    assert client.post(VER, json={"owner_email": email, "code": code}).status_code == 201
    replay = client.post(VER, json={"owner_email": email, "code": code})
    assert replay.status_code == 401                                     # consumed: no second organization
    assert client.get("/api/v1/auth/me").status_code == 401


def test_verify_without_any_request(client: TestClient, mailbox) -> None:
    assert client.post(VER, json={"owner_email": _email(), "code": "123456"}).status_code == 401


# ---------------------------------------------------------------- throttling and enumeration
def test_resend_cooldown_and_hourly_cap(client: TestClient, mailbox, db_session) -> None:
    email = _email()
    assert _request(client, email).status_code == 202
    again = _request(client, email)
    assert again.status_code == 429 and again.headers["retry-after"]
    for _ in range(signup_code_service.MAX_PER_EMAIL_PER_HOUR):          # age the rows past the cooldown
        db_session.execute(text("UPDATE signup_codes SET created_at = created_at - interval '5 minutes' WHERE email = :e"), {"e": email})
        db_session.flush()
        r = _request(client, email)
    assert r.status_code == 429 and "Too many" in r.text


def test_an_existing_email_gets_the_same_answer_and_no_code(client: TestClient, mailbox, register_org, db_session) -> None:
    org = register_org()
    existing = db_session.execute(text("SELECT email FROM users WHERE organization_id = :o LIMIT 1"),
                                  {"o": str(org["organization"]["id"])}).scalar_one()
    before = len(mailbox)
    r = _request(client, existing)
    assert r.status_code == 202 and r.json()["status"] == "code_sent"     # identical answer: no enumeration
    assert len(mailbox) == before                                        # but nothing was sent
    assert db_session.execute(select(SignupCode).where(SignupCode.email == existing)).scalar_one_or_none() is None


def test_email_taken_between_request_and_verify(client: TestClient, mailbox) -> None:
    email = _email()
    _request(client, email)
    code = _code(mailbox)
    client.post("/api/v1/auth/register-organization", json={"organization_name": "Other", "owner_email": email,
                "owner_name": "Other", "owner_password": "other-owner-pass-1"})
    assert client.post(VER, json={"owner_email": email, "code": code}).status_code == 409


def test_without_email_delivery_the_answer_is_honest(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(signup_code_service.email_delivery, "is_configured", lambda: False)
    r = _request(client, _email())
    assert r.status_code == 503 and "not configured" in r.text


def test_validation(client: TestClient, mailbox) -> None:
    assert client.post(REQ, json={"organization_name": "A", "owner_email": _email(), "owner_name": "X"}).status_code == 422
    assert client.post(REQ, json={"organization_name": "Valid Co", "owner_email": "not-an-email", "owner_name": "X"}).status_code == 422
    assert client.post(VER, json={"owner_email": _email(), "code": "12345"}).status_code == 422


# ---------------------------------------------------------------- tenant isolation
def test_two_signups_are_separate_tenants(client: TestClient, mailbox) -> None:
    a, b = _email(), _email()
    _request(client, a); ca = _code(mailbox)
    _request(client, b); cb = _code(mailbox)
    ra = client.post(VER, json={"owner_email": a, "code": ca}).json()
    rb = client.post(VER, json={"owner_email": b, "code": cb}).json()
    assert ra["organization"]["id"] != rb["organization"]["id"]
    ha = {"Authorization": f"Bearer {ra['token']['access_token']}"}
    hb = {"Authorization": f"Bearer {rb['token']['access_token']}"}
    ko = client.post("/api/v1/knowledge", headers=ha, json={"canonical_name": "Private KO", "object_type": "ingredient"}).json()
    assert client.get(f"/api/v1/knowledge/{ko['id']}", headers=hb).status_code == 404
    assert client.get("/api/v1/knowledge", headers=hb).json()["total"] == 0
