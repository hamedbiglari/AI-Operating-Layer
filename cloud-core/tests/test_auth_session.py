"""Browser session: HttpOnly refresh cookie + short-lived in-memory access token (ADR-129).

What these tests are actually defending:
  - the cookie is unreadable to page scripts and never reaches a non-session route
  - rotation really invalidates the previous cookie
  - replaying a rotated cookie kills the session rather than being tolerated
  - nothing about /login, /login-code/verify or the bearer flow changed
"""
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.auth_session import AuthSession
from app.services import email_delivery

COOKIE = settings.SESSION_COOKIE_NAME
PATH = settings.session_cookie_path


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.invalid")
    monkeypatch.setattr(email_delivery, "send", lambda **kw: sent.append(kw))
    return sent


def _code(outbox):
    return re.search(r"\b(\d{6})\b", outbox[-1]["body"]).group(1)


def _open(client, register_org, outbox):
    """Sign in through the browser-session route and return (org, email, response)."""
    org = register_org()
    email = org["user"]["email"]
    assert client.post("/api/v1/auth/login-code/request", json={"email": email}).status_code == 202
    response = client.post("/api/v1/auth/session", json={"email": email, "code": _code(outbox)})
    assert response.status_code == 200, response.text
    return org, email, response


def _cookie(client):
    return client.cookies.get(COOKIE, path=PATH)


def _use_cookie(client, value):
    """Replace the jar outright. `client.cookies.set` appends, so without this the stale cookie is
    sent alongside the one under test and the server answers about the wrong one."""
    client.cookies.clear()
    client.cookies.set(COOKIE, value, path=PATH)


def _last_session(db_session):
    return db_session.execute(select(AuthSession)).scalars().all()[-1]


# --- opening a session ------------------------------------------------------------


def test_opening_a_session_returns_a_token_in_the_body_and_a_cookie_in_the_header(
        client, register_org, outbox):
    _, email, response = _open(client, register_org, outbox)
    body = response.json()
    # The access token is in the body, where only the caller's script can see it — never in a cookie,
    # which would survive the tab and be sent automatically.
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["expires_in_minutes"] == settings.BROWSER_ACCESS_TOKEN_EXPIRE_MINUTES
    assert body["access_token"] not in response.headers.get("set-cookie", "")

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["user"]["email"] == email


def test_the_session_cookie_is_httponly_scoped_and_not_readable_by_a_page(client, register_org, outbox):
    _, _, response = _open(client, register_org, outbox)
    header = response.headers.get("set-cookie", "").lower()
    assert "httponly" in header, "a script-readable session cookie defeats the entire arrangement"
    assert f"path={PATH}".lower() in header
    assert f"samesite={settings.SESSION_COOKIE_SAMESITE}".lower() in header
    assert _cookie(client)


def test_the_browser_access_token_is_shorter_lived_than_the_api_one(client, register_org, outbox):
    import jwt

    _, _, response = _open(client, register_org, outbox)
    claims = jwt.decode(response.json()["access_token"], settings.SECRET_KEY,
                        algorithms=[settings.ALGORITHM])
    lifetime = claims["exp"] - claims["iat"]
    assert lifetime <= settings.BROWSER_ACCESS_TOKEN_EXPIRE_MINUTES * 60 + 2
    assert lifetime < settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def test_a_wrong_code_opens_no_session(client, register_org, outbox):
    org = register_org()
    email = org["user"]["email"]
    client.post("/api/v1/auth/login-code/request", json={"email": email})
    response = client.post("/api/v1/auth/session", json={"email": email, "code": "000000"})
    assert response.status_code == 401
    assert COOKIE not in response.headers.get("set-cookie", "")


def test_only_a_hash_of_the_secret_is_stored(client, register_org, outbox, db_session):
    _open(client, register_org, outbox)
    secret = _cookie(client).split(".", 1)[1]
    row = _last_session(db_session)
    # Reading the table must not hand anyone a usable cookie.
    assert secret not in row.token_hash
    assert re.fullmatch(r"[0-9a-f]{64}", row.token_hash)


# --- refreshing -------------------------------------------------------------------


def test_refresh_issues_a_new_token_and_rotates_the_cookie(client, register_org, outbox):
    _open(client, register_org, outbox)
    first = _cookie(client)
    response = client.post("/api/v1/auth/session/refresh")
    assert response.status_code == 200, response.text
    second = _cookie(client)
    assert second and second != first, "the cookie must rotate, or a stolen one lives as long as the session"
    assert first.split(".")[0] == second.split(".")[0], "rotation replaces the secret, not the session"
    me = client.get("/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert me.status_code == 200


def test_replaying_a_rotated_cookie_kills_the_session(client, register_org, outbox, db_session):
    _open(client, register_org, outbox)
    stolen = _cookie(client)
    assert client.post("/api/v1/auth/session/refresh").status_code == 200
    live = _cookie(client)

    # Past the few seconds allowed for a concurrent refresh, so this is a replay and nothing else.
    row = _last_session(db_session)
    row.previous_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()

    _use_cookie(client, stolen)
    assert client.post("/api/v1/auth/session/refresh").status_code == 401

    # The legitimate browser is signed out too: with two copies in circulation there is no way to
    # tell which caller is the real one.
    _use_cookie(client, live)
    assert client.post("/api/v1/auth/session/refresh").status_code == 401
    db_session.refresh(row)
    assert row.revoked_reason == "reuse_detected" and row.revoked_at is not None


def test_two_tabs_refreshing_together_are_not_treated_as_a_replay(client, register_org, outbox,
                                                                  db_session):
    """Both tabs hold the cookie the browser had. That is ordinary, and signing the person out for
    it would be a bug rather than security."""
    _open(client, register_org, outbox)
    shared = _cookie(client)

    assert client.post("/api/v1/auth/session/refresh").status_code == 200   # first tab
    _use_cookie(client, shared)                          # second tab, same cookie
    assert client.post("/api/v1/auth/session/refresh").status_code == 200

    row = _last_session(db_session)
    assert row.revoked_at is None and row.rotations == 2
    # And the newest cookie still works afterwards.
    assert client.post("/api/v1/auth/session/refresh").status_code == 200


def test_a_cookie_older_than_the_grace_window_still_kills_the_session(client, register_org, outbox,
                                                                      db_session):
    _open(client, register_org, outbox)
    stolen = _cookie(client)
    assert client.post("/api/v1/auth/session/refresh").status_code == 200

    row = _last_session(db_session)
    row.previous_until = datetime.now(timezone.utc) - timedelta(seconds=1)   # window has passed
    db_session.flush()

    _use_cookie(client, stolen)
    assert client.post("/api/v1/auth/session/refresh").status_code == 401
    db_session.refresh(row)
    assert row.revoked_reason == "reuse_detected"


def test_a_secret_two_rotations_old_kills_the_session_even_inside_the_window(
        client, register_org, outbox, db_session):
    """Only the immediately preceding secret is forgiven; anything older is a replay."""
    _open(client, register_org, outbox)
    oldest = _cookie(client)
    assert client.post("/api/v1/auth/session/refresh").status_code == 200
    assert client.post("/api/v1/auth/session/refresh").status_code == 200

    _use_cookie(client, oldest)
    assert client.post("/api/v1/auth/session/refresh").status_code == 401
    assert _last_session(db_session).revoked_reason == "reuse_detected"


def test_refresh_without_a_cookie_is_401(client):
    client.cookies.clear()
    assert client.post("/api/v1/auth/session/refresh").status_code == 401


def test_a_forged_cookie_is_401(client, register_org, outbox):
    _open(client, register_org, outbox)
    session_id = _cookie(client).split(".")[0]
    _use_cookie(client, f"{session_id}.not-the-secret")
    assert client.post("/api/v1/auth/session/refresh").status_code == 401


@pytest.mark.parametrize("value", ["garbage", "no-dot", "not-a-uuid.secret", "aaaaaaaa.x.y"])
def test_a_malformed_cookie_is_401_and_never_an_error(client, value):
    _use_cookie(client, value)
    assert client.post("/api/v1/auth/session/refresh").status_code == 401


def test_an_expired_session_cannot_be_refreshed(client, register_org, outbox, db_session):
    _open(client, register_org, outbox)
    row = _last_session(db_session)
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()
    response = client.post("/api/v1/auth/session/refresh")
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


def test_rotation_does_not_extend_the_absolute_lifetime(client, register_org, outbox, db_session):
    _open(client, register_org, outbox)
    row = _last_session(db_session)
    before = row.expires_at
    assert client.post("/api/v1/auth/session/refresh").status_code == 200
    db_session.refresh(row)
    assert row.expires_at == before, "a stolen cookie must not be refreshable forever"
    assert row.rotations == 1


# --- signing out ------------------------------------------------------------------


def test_signing_out_revokes_the_session_and_clears_the_cookie(client, register_org, outbox, db_session):
    _open(client, register_org, outbox)
    response = client.delete("/api/v1/auth/session")
    assert response.status_code == 204
    assert not _cookie(client)
    assert _last_session(db_session).revoked_reason == "logout"
    assert client.post("/api/v1/auth/session/refresh").status_code == 401


def test_signing_out_twice_is_not_an_error(client, register_org, outbox):
    _open(client, register_org, outbox)
    assert client.delete("/api/v1/auth/session").status_code == 204
    assert client.delete("/api/v1/auth/session").status_code == 204


def test_signing_out_with_a_wrong_secret_revokes_nothing(client, register_org, outbox, db_session):
    _open(client, register_org, outbox)
    real = _cookie(client)
    _use_cookie(client, f"{real.split('.')[0]}.wrong")
    assert client.delete("/api/v1/auth/session").status_code == 204
    assert _last_session(db_session).revoked_at is None

    _use_cookie(client, real)
    assert client.post("/api/v1/auth/session/refresh").status_code == 200


def test_the_database_refuses_a_revoked_session_with_no_reason(client, register_org, outbox,
                                                                db_session):
    """The vocabulary holds in the schema, not only in the service that writes it."""
    import pytest as _pytest
    from sqlalchemy.exc import IntegrityError

    _open(client, register_org, outbox)
    row = _last_session(db_session)
    row.revoked_at = datetime.now(timezone.utc)
    row.revoked_reason = None
    with _pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_the_database_refuses_an_invented_revocation_reason(client, register_org, outbox, db_session):
    import pytest as _pytest
    from sqlalchemy.exc import IntegrityError

    _open(client, register_org, outbox)
    row = _last_session(db_session)
    row.revoked_at = datetime.now(timezone.utc)
    row.revoked_reason = "because"
    with _pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- the cookie is not an authentication mechanism anywhere else -------------------


def test_the_session_cookie_alone_does_not_authenticate_a_chat_or_api_call(client, register_org, outbox):
    _open(client, register_org, outbox)
    # The cookie is scoped to /auth/session, so the browser would not even send it here — and the
    # server would not accept it if it did. Only the bearer token works.
    for url in ("/api/v1/auth/me", "/api/v1/chat/config", "/api/v1/chat/conversations"):
        assert client.get(url).status_code == 401, f"{url} accepted a cookie as credentials"


def test_the_existing_bearer_login_routes_are_unchanged(client, register_org, outbox):
    org = register_org()
    email = org["user"]["email"]
    client.post("/api/v1/auth/login-code/request", json={"email": email})
    response = client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": _code(outbox)})
    assert response.status_code == 200
    assert response.json()["expires_in_minutes"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES
    assert COOKIE not in response.headers.get("set-cookie", ""), \
        "the pre-existing bearer route must not start setting cookies"
