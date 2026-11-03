"""Official client suite backend (ADR-137): native session, chat idempotency, client config.

What these tests defend:
  - a native client gets the same auth_sessions guarantees as the browser (rotation, reuse detection,
    sign-out) with the refresh secret in the body, and never a cookie
  - a lost reply re-sent with the same client_request_id returns the stored turn, never asks twice
  - /clients/config reports only configured links and published releases, and never invents one
"""
from __future__ import annotations

import json
import re
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.auth_session import AuthSession
from app.models.conversation import Conversation, ConversationMessage
from app.services import email_delivery

N = "/api/v1/auth/native/session"
TERMS = {"accept_terms": True, "terms_version": settings.CLIENT_TERMS_VERSION, "client_platform": "windows"}
C = "/api/v1/chat"


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.invalid")
    monkeypatch.setattr(email_delivery, "send", lambda **kw: sent.append(kw))
    return sent


def _code(outbox):
    return re.search(r"\b(\d{8})\b", outbox[-1]["body"]).group(1)


def _native_by_code(client, register_org, outbox):
    org = register_org()
    email = org["user"]["email"]
    req = client.post("/api/v1/auth/login-code/request", json={"email": email})
    assert req.status_code == 202
    r = client.post(N, json={"grant": "login_code", "email": email, "challenge": req.json()["challenge"],
                             "code": _code(outbox), **TERMS},
                    headers={"User-Agent": "AIOL-Desktop/0.1.0 (windows)"})
    assert r.status_code == 200, r.text
    return org, r


# ------------------------------------------------------------------ native session
def test_native_sign_in_with_a_code_returns_both_tokens_in_the_body_and_sets_no_cookie(
        client, register_org, outbox):
    org, r = _native_by_code(client, register_org, outbox)
    body = r.json()
    assert body["access_token"] and body["refresh_token"] and body["token_type"] == "bearer"
    assert body["expires_in_minutes"] == settings.NATIVE_ACCESS_TOKEN_EXPIRE_MINUTES
    assert "set-cookie" not in r.headers, "a native client must never depend on a cookie"
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["user"]["email"] == org["user"]["email"]


def test_native_sign_in_with_a_password(client, register_org):
    org = register_org()
    r = client.post(N, json={"grant": "password", "email": org["user"]["email"], "password": org["password"], **TERMS})
    assert r.status_code == 200, r.text
    bad = client.post(N, json={"grant": "password", "email": org["user"]["email"], "password": "wrong-password", **TERMS})
    assert bad.status_code == 401 and "refresh_token" not in bad.text


def test_a_grant_without_its_secret_is_refused(client, register_org):
    org = register_org()
    assert client.post(N, json={"grant": "password", "email": org["user"]["email"], **TERMS}).status_code == 422
    assert client.post(N, json={"grant": "login_code", "email": org["user"]["email"], **TERMS}).status_code == 422
    # SEC-login-code-lockout: a code without the challenge it was issued with is refused before any check.
    assert client.post(N, json={"grant": "login_code", "email": org["user"]["email"], "code": "12345678",
                                **TERMS}).status_code == 422


def test_only_the_hash_of_the_refresh_secret_is_stored(client, register_org, outbox, db_session):
    _, r = _native_by_code(client, register_org, outbox)
    sid, secret = r.json()["refresh_token"].split(".", 1)
    row = db_session.get(AuthSession, uuid.UUID(sid))
    assert secret not in row.token_hash and len(row.token_hash) == 64
    assert row.user_agent.startswith("AIOL-Desktop/0.1.0")


def test_refresh_rotates_and_the_old_secret_dies(client, register_org, outbox, db_session, monkeypatch):
    from app.services import auth_session_service
    from datetime import timedelta

    monkeypatch.setattr(auth_session_service, "_ROTATION_GRACE", timedelta(seconds=0))
    _, r = _native_by_code(client, register_org, outbox)
    first = r.json()["refresh_token"]
    r2 = client.post(f"{N}/refresh", json={"refresh_token": first})
    assert r2.status_code == 200, r2.text
    second = r2.json()["refresh_token"]
    assert second != first
    # Replaying the rotated-away secret is a stolen copy: the whole session is revoked.
    replay = client.post(f"{N}/refresh", json={"refresh_token": first})
    assert replay.status_code == 401
    assert client.post(f"{N}/refresh", json={"refresh_token": second}).status_code == 401
    row = db_session.get(AuthSession, uuid.UUID(first.split(".", 1)[0]))
    db_session.refresh(row)
    assert row.revoked_reason == "reuse_detected"


def test_sign_out_ends_the_session_and_is_idempotent(client, register_org, outbox):
    _, r = _native_by_code(client, register_org, outbox)
    token = r.json()["refresh_token"]
    assert client.post(f"{N}/end", json={"refresh_token": token}).status_code == 204
    assert client.post(f"{N}/end", json={"refresh_token": token}).status_code == 204
    assert client.post(f"{N}/refresh", json={"refresh_token": token}).status_code == 401


def test_a_forged_refresh_token_is_refused(client):
    assert client.post(f"{N}/refresh", json={"refresh_token": f"{uuid.uuid4()}.forged-secret"}).status_code == 401
    assert client.post(f"{N}/refresh", json={"refresh_token": "not-a-session-token"}).status_code == 401


def test_the_refresh_token_is_not_a_bearer_token(client, register_org, outbox):
    _, r = _native_by_code(client, register_org, outbox)
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {r.json()['refresh_token']}"}).status_code == 401


# ------------------------------------------------------------------ chat idempotency
def _chat_ready(client, register_org):
    org = register_org()
    h = org["headers"]
    assert client.put(f"{C}/settings", headers=h, json={"enabled": True}).status_code == 200
    convo = client.post(f"{C}/conversations", headers=h, json={}).json()
    return org, h, convo


def test_resending_a_question_with_the_same_key_returns_the_stored_answer(client, register_org, db_session):
    _, h, convo = _chat_ready(client, register_org)
    body = {"question": "What is Taranjabin?", "client_request_id": "req_0001abcd"}
    first = client.post(f"{C}/conversations/{convo['id']}/messages", headers=h, json=body)
    assert first.status_code == 201, first.text
    again = client.post(f"{C}/conversations/{convo['id']}/messages", headers=h, json=body)
    assert again.status_code == 200 and again.headers.get("Idempotent-Replay") == "true"
    assert again.json()["id"] == first.json()["id"]
    row = db_session.get(Conversation, uuid.UUID(convo["id"]))
    db_session.refresh(row)
    assert row.message_count == 2, "the question must be stored once and answered once"


def test_a_keyed_question_still_being_answered_is_409_not_a_second_ask(client, register_org, db_session):
    _, h, convo = _chat_ready(client, register_org)
    row = db_session.get(Conversation, uuid.UUID(convo["id"]))
    row.message_count += 1
    db_session.add(ConversationMessage(organization_id=row.organization_id, conversation_id=row.id,
                                       position=row.message_count, role="user", text="q",
                                       client_request_id="req_inflight1"))
    db_session.flush()
    r = client.post(f"{C}/conversations/{convo['id']}/messages", headers=h,
                    json={"question": "q", "client_request_id": "req_inflight1"})
    assert r.status_code == 409 and r.json()["error"]["reason"] == "request_in_progress"


def test_the_same_key_in_another_users_conversation_is_independent(client, register_org):
    _, h1, c1 = _chat_ready(client, register_org)
    _, h2, c2 = _chat_ready(client, register_org)
    body = {"question": "q", "client_request_id": "req_shared_key"}
    a = client.post(f"{C}/conversations/{c1['id']}/messages", headers=h1, json=body)
    b = client.post(f"{C}/conversations/{c2['id']}/messages", headers=h2, json=body)
    assert a.status_code == b.status_code == 201 and a.json()["id"] != b.json()["id"]
    # And a key cannot be used to read someone else's turn through their conversation id.
    assert client.post(f"{C}/conversations/{c1['id']}/messages", headers=h2, json=body).status_code == 404


def test_a_malformed_key_is_refused(client, register_org):
    _, h, convo = _chat_ready(client, register_org)
    r = client.post(f"{C}/conversations/{convo['id']}/messages", headers=h,
                    json={"question": "q", "client_request_id": "has spaces and ; semicolons"})
    assert r.status_code == 422


def test_questions_without_a_key_behave_exactly_as_before(client, register_org):
    _, h, convo = _chat_ready(client, register_org)
    a = client.post(f"{C}/conversations/{convo['id']}/messages", headers=h, json={"question": "q"})
    b = client.post(f"{C}/conversations/{convo['id']}/messages", headers=h, json={"question": "q"})
    assert a.status_code == b.status_code == 201 and a.json()["id"] != b.json()["id"]


# ------------------------------------------------------------------ client config
def test_client_config_is_public_and_invents_nothing(client, monkeypatch):
    for name in ("CLIENT_HELP_URL", "CLIENT_UPGRADE_URL", "CLIENT_PRIVACY_URL"):
        monkeypatch.setattr(settings, name, None)
    monkeypatch.setattr(settings, "CLIENT_RELEASES_JSON", "")
    body = client.get("/api/v1/clients/config").json()
    assert body["links"]["help"] is None and body["links"]["privacy"] is None
    assert body["upgrade"] == {"url": None, "state": "not_configured"}
    assert body["releases"] == []
    assert body["languages"] == ["en", "fa"]


def test_client_config_reports_configured_links_and_drops_unsafe_ones(client, monkeypatch):
    monkeypatch.setattr(settings, "CLIENT_HELP_URL", "https://help.example.dev/")
    monkeypatch.setattr(settings, "CLIENT_PRIVACY_URL", "javascript:alert(1)")
    monkeypatch.setattr(settings, "CLIENT_TERMS_URL", "file:///etc/passwd")
    links = client.get("/api/v1/clients/config").json()["links"]
    assert links["help"] == "https://help.example.dev/"
    assert links["privacy"] is None and links["terms"] is None


def test_upgrade_is_withheld_on_platforms_without_a_reviewed_purchase_flow(client, monkeypatch):
    monkeypatch.setattr(settings, "CLIENT_UPGRADE_URL", "https://app.example.dev/billing")
    monkeypatch.setattr(settings, "CLIENT_UPGRADE_PLATFORMS", "web,windows,macos")
    assert client.get("/api/v1/clients/config?platform=windows").json()["upgrade"]["state"] == "available"
    ios = client.get("/api/v1/clients/config?platform=ios").json()["upgrade"]
    assert ios == {"url": None, "state": "not_offered_on_platform"}


def test_releases_list_only_well_formed_entries_and_available_needs_a_url(client, monkeypatch):
    monkeypatch.setattr(settings, "CLIENT_RELEASES_JSON", (
        '[{"platform": "windows", "status": "AVAILABLE", "version": "0.1.0", "url": "https://dl.example.dev/w.exe"},'
        ' {"platform": "macos", "status": "AVAILABLE", "version": "0.1.0"},'
        ' {"platform": "linux", "status": "AVAILABLE", "url": "https://x.dev"},'
        ' {"platform": "ios", "status": "COMING_SOON"}]'))
    rel = client.get("/api/v1/clients/config").json()["releases"]
    assert [(r["platform"], r["status"]) for r in rel] == [("windows", "AVAILABLE"), ("ios", "COMING_SOON")]
    monkeypatch.setattr(settings, "CLIENT_RELEASES_JSON", "{not json")
    assert client.get("/api/v1/clients/config").json()["releases"] == []


def test_production_refuses_non_https_client_links():
    from app.core.config import InsecureProductionConfigError, Settings

    with pytest.raises(InsecureProductionConfigError, match="CLIENT_HELP_URL"):
        Settings(APP_ENV="production", SECRET_KEY="x" * 40,
                 DATABASE_URL="postgresql+psycopg://u:p@db/aiol", CLIENT_HELP_URL="http://help.example.dev")


# ------------------------------------------------------------------ terms acceptance at sign-in (ADR-139)
def test_sign_in_without_ticking_the_terms_is_refused_before_credentials_are_checked(client, register_org):
    org = register_org()
    base = {"grant": "password", "email": org["user"]["email"], "password": org["password"]}
    for extra in ({}, {"accept_terms": False, "terms_version": settings.CLIENT_TERMS_VERSION},
                  {"accept_terms": True, "terms_version": "1999-01-01"}, {"accept_terms": True}):
        r = client.post(N, json={**base, **extra})
        assert r.status_code == 409, extra
        assert r.json()["error"]["reason"] == "terms_not_accepted"
        assert r.json()["error"]["terms_version"] == settings.CLIENT_TERMS_VERSION
        assert "refresh_token" not in r.text


def test_accepting_records_one_row_per_version_with_everything_the_tick_covered(client, register_org, db_session):
    from app.models.audit_log import AuditLog
    from app.models.legal_acceptance import LegalAcceptance

    org = register_org()
    body = {"grant": "password", "email": org["user"]["email"], "password": org["password"], **TERMS}
    assert client.post(N, json=body).status_code == 200
    assert client.post(N, json=body).status_code == 200
    rows = db_session.execute(select(LegalAcceptance).where(
        LegalAcceptance.user_id == uuid.UUID(org["user"]["id"]))).scalars().all()
    assert len(rows) == 1, "signing in again does not duplicate the acceptance"
    assert rows[0].terms_version == settings.CLIENT_TERMS_VERSION
    assert rows[0].consents == ["terms", "privacy", "device_intelligence"]
    assert rows[0].client_platform == "windows"
    assert db_session.execute(select(AuditLog).where(AuditLog.action == "legal.terms_accepted")).scalars().first()


def test_a_failed_password_records_no_acceptance(client, register_org, db_session):
    from app.models.legal_acceptance import LegalAcceptance

    org = register_org()
    r = client.post(N, json={"grant": "password", "email": org["user"]["email"], "password": "nope-nope", **TERMS})
    assert r.status_code == 401
    assert db_session.execute(select(LegalAcceptance).where(
        LegalAcceptance.user_id == uuid.UUID(org["user"]["id"]))).first() is None


def test_client_config_publishes_the_terms_version(client):
    terms = client.get("/api/v1/clients/config").json()["terms"]
    assert terms == {"version": settings.CLIENT_TERMS_VERSION, "consents": ["terms", "privacy", "device_intelligence"]}


# ------------------------------------------------------------------ streaming (ADR-137 §streaming)
def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = [x for x in block.split("\n") if not x.startswith(":")]
        if not lines:
            continue
        name = lines[0].split(": ", 1)[1]
        data = json.loads(lines[1].split(": ", 1)[1])
        out.append((name, data))
    return out


def test_streaming_emits_progress_then_the_same_stored_message(client, register_org, db_session):
    _, h, convo = _chat_ready(client, register_org)
    r = client.post(f"{C}/conversations/{convo['id']}/messages/stream", headers=h,
                    json={"question": "What is Taranjabin?", "client_request_id": "req_stream001"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = _events(r.text)
    names = [n for n, _ in ev]
    assert names[0] == "accepted" and names[-1] == "message", names
    msg = ev[-1][1]
    assert msg["role"] == "assistant" and msg["answer_state"] == "NEEDS_USER_SOURCE"
    stored = client.get(f"{C}/conversations/{convo['id']}/messages", headers=h).json()["items"]
    assert msg["id"] in {m["id"] for m in stored}, "the streamed message is the stored one"


def test_streaming_replays_a_known_request_without_asking_again(client, register_org, db_session):
    _, h, convo = _chat_ready(client, register_org)
    body = {"question": "q", "client_request_id": "req_stream002"}
    first = _events(client.post(f"{C}/conversations/{convo['id']}/messages/stream", headers=h, json=body).text)[-1][1]
    again = client.post(f"{C}/conversations/{convo['id']}/messages/stream", headers=h, json=body)
    assert again.headers.get("Idempotent-Replay") == "true"
    assert _events(again.text) == [("message", first)]
    row = db_session.get(Conversation, uuid.UUID(convo["id"]))
    db_session.refresh(row)
    assert row.message_count == 2


def test_streaming_refuses_before_opening_the_stream(client, register_org):
    _, h, convo = _chat_ready(client, register_org)
    _, h2, _ = _chat_ready(client, register_org)
    assert client.post(f"{C}/conversations/{convo['id']}/messages/stream", headers=h2,
                       json={"question": "q"}).status_code == 404
    assert client.post(f"{C}/conversations/{convo['id']}/messages/stream", json={"question": "q"}).status_code == 401
    client.post(f"{C}/conversations/{convo['id']}/archive", headers=h)
    assert client.post(f"{C}/conversations/{convo['id']}/messages/stream", headers=h,
                       json={"question": "q"}).status_code == 409


def test_a_refusal_inside_the_pipeline_becomes_an_error_event(client, register_org):
    org, h, convo = _chat_ready(client, register_org)
    client.put(f"{C}/settings", headers=h, json={"messages_per_user_per_day": 1})
    client.post(f"{C}/conversations/{convo['id']}/messages", headers=h, json={"question": "one"})
    ev = _events(client.post(f"{C}/conversations/{convo['id']}/messages/stream", headers=h,
                             json={"question": "two"}).text)
    assert ev[-1][0] == "error" and ev[-1][1]["status"] == 429


# ------------------------------------------------------------------ signed desktop updates (ADR-140)
U = "/api/v1/clients/updates"
SIG = "dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZSBmcm9tIHRhdXJpIHNlY3JldCBrZXkK" * 2


def _updates(monkeypatch, entries):
    monkeypatch.setattr(settings, "CLIENT_UPDATES_JSON", json.dumps(entries))


def test_no_configured_update_is_204(client, monkeypatch):
    monkeypatch.setattr(settings, "CLIENT_UPDATES_JSON", "")
    assert client.get(f"{U}/windows/x86_64/0.1.0").status_code == 204


def test_a_newer_signed_release_is_offered(client, monkeypatch):
    _updates(monkeypatch, {"windows-x86_64": {"version": "0.2.0", "url": "https://dl.aiol.example/AIOL_0.2.0.msi",
                                              "signature": SIG, "notes": "Fixes", "pub_date": "2026-11-01T00:00:00Z"}})
    r = client.get(f"{U}/windows/x86_64/0.1.0")
    assert r.status_code == 200
    assert r.json() == {"version": "0.2.0", "url": "https://dl.aiol.example/AIOL_0.2.0.msi", "signature": SIG,
                        "notes": "Fixes", "pub_date": "2026-11-01T00:00:00Z"}


def test_same_older_unsigned_or_insecure_releases_are_never_offered(client, monkeypatch):
    good = {"version": "0.2.0", "url": "https://dl.aiol.example/a.msi", "signature": SIG}
    for entry, current in ((good, "0.2.0"), (good, "0.3.0"), ({**good, "signature": ""}, "0.1.0"),
                           ({**good, "url": "http://dl.aiol.example/a.msi"}, "0.1.0"),
                           ({**good, "version": "banana"}, "0.1.0"), (good, "not-a-version")):
        _updates(monkeypatch, {"windows-x86_64": entry})
        assert client.get(f"{U}/windows/x86_64/{current}").status_code == 204, (entry, current)
    _updates(monkeypatch, {"windows-x86_64": good})
    assert client.get(f"{U}/linux/x86_64/0.1.0").status_code == 204
    assert client.get(f"{U}/windows/sparc/0.1.0").status_code == 204
    monkeypatch.setattr(settings, "CLIENT_UPDATES_JSON", "{broken")
    assert client.get(f"{U}/windows/x86_64/0.1.0").status_code == 204
