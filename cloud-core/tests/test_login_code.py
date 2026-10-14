"""Email one-time login code — owner rules (P13 addendum 9; Phase 14 §33).
Delivery is replaced by a capturing function here ONLY; runtime delivery is
verified separately against a real SMTP server."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.services import email_delivery

PW = "correct-horse-battery"


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.invalid")
    monkeypatch.setattr(email_delivery, "send", lambda **kw: sent.append(kw))
    return sent


def _code(outbox):
    return re.search(r"\b(\d{6})\b", outbox[-1]["body"]).group(1)


def _user(register_org):
    org = register_org()
    return org, org["user"]["email"]


def test_code_login_issues_a_working_token(client, register_org, outbox):
    org, email = _user(register_org)
    r = client.post("/api/v1/auth/login-code/request", json={"email": email})
    assert r.status_code == 202 and len(outbox) == 1 and outbox[0]["to"] == email
    code = _code(outbox)
    assert len(code) == 6 and code not in r.text
    tok = client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": code}).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["user"]["email"] == email and me["organization"]["id"] == org["organization"]["id"]


def test_code_is_single_use(client, register_org, outbox):
    _, email = _user(register_org)
    client.post("/api/v1/auth/login-code/request", json={"email": email}); code = _code(outbox)
    assert client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": code}).status_code == 200
    assert client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": code}).status_code == 401


def test_resend_is_blocked_for_five_minutes(client, register_org, outbox):
    _, email = _user(register_org)
    assert client.post("/api/v1/auth/login-code/request", json={"email": email}).status_code == 202
    r = client.post("/api/v1/auth/login-code/request", json={"email": email})
    assert r.status_code == 429 and 0 < int(r.headers["Retry-After"]) <= 301 and len(outbox) == 1


def test_expired_code_is_rejected(client, register_org, outbox, db_session):
    _, email = _user(register_org)
    client.post("/api/v1/auth/login-code/request", json={"email": email}); code = _code(outbox)
    db_session.execute(text("UPDATE login_codes SET expires_at = now() - interval '1 second'"))
    db_session.flush()
    assert client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": code}).status_code == 401


def test_three_wrong_codes_lock_for_one_hour_then_twenty_four(client, register_org, outbox, db_session):
    _, email = _user(register_org)
    client.post("/api/v1/auth/login-code/request", json={"email": email}); code = _code(outbox)
    wrong = "000000" if code != "000000" else "111111"
    codes = [client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": wrong}).status_code for _ in range(3)]
    assert codes == [401, 401, 423]
    r = client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": code})
    assert r.status_code == 423 and 3500 <= int(r.headers["Retry-After"]) <= 3600   # even the right code is refused
    assert "1 hour" in r.text
    # the hour passes
    db_session.execute(text("UPDATE login_code_throttles SET locked_until = now() - interval '1 second', "
                            "resend_available_at = NULL"))
    db_session.flush()
    client.post("/api/v1/auth/login-code/request", json={"email": email}); code2 = _code(outbox)
    wrong = "000000" if code2 != "000000" else "111111"
    codes = [client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": wrong}).status_code for _ in range(3)]
    assert codes == [401, 401, 423]
    r = client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": code2})
    assert r.status_code == 423 and int(r.headers["Retry-After"]) > 86000 and "contact support" in r.text


def test_unknown_email_is_indistinguishable_and_sends_nothing(client, outbox):
    r = client.post("/api/v1/auth/login-code/request", json={"email": "nobody@example.com"})
    assert r.status_code == 202 and outbox == []


def test_no_delivery_configured_means_no_code_and_honest_error(client, register_org, monkeypatch, db_session):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    _, email = _user(register_org)
    r = client.post("/api/v1/auth/login-code/request", json={"email": email})
    assert r.status_code == 503
    assert db_session.execute(text("SELECT count(*) FROM login_codes")).scalar_one() == 0


def test_code_is_stored_only_as_a_keyed_hash(client, register_org, outbox, db_session):
    _, email = _user(register_org)
    client.post("/api/v1/auth/login-code/request", json={"email": email}); code = _code(outbox)
    stored = db_session.execute(text("SELECT code_hash FROM login_codes")).scalars().all()
    assert stored and all(code not in h and len(h) == 64 for h in stored)


def test_code_for_one_user_does_not_open_another_account(client, register_org, outbox):
    _, email_a = _user(register_org)
    _, email_b = _user(register_org)
    client.post("/api/v1/auth/login-code/request", json={"email": email_a}); code_a = _code(outbox)
    assert client.post("/api/v1/auth/login-code/verify", json={"email": email_b, "code": code_a}).status_code == 401
