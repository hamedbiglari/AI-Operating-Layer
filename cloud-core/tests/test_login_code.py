"""Email one-time login code — owner rules (P13 addendum 9; Phase 14 §33), as changed by SEC-login-code-lockout
(option B, migration 0059): every code is bound to the challenge returned when it was requested, wrong guesses
count against that one code, nothing ever locks the account, and sending is limited to 5 codes per address per
rolling hour. Codes have 8 digits.
Delivery is replaced by a capturing function here ONLY; runtime delivery is
verified separately against a real SMTP server."""
import re
import uuid

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.services import email_delivery

REQUEST, VERIFY = "/api/v1/auth/login-code/request", "/api/v1/auth/login-code/verify"


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.invalid")
    monkeypatch.setattr(email_delivery, "send", lambda **kw: sent.append(kw))
    return sent


def _code(outbox):
    return re.search(r"\b(\d{8})\b", outbox[-1]["body"]).group(1)


def _user(register_org):
    org = register_org()
    return org, org["user"]["email"]


def _request(client, email):
    r = client.post(REQUEST, json={"email": email})
    return r, r.json().get("challenge") if r.status_code == 202 else None


def _verify(client, email, challenge, code):
    return client.post(VERIFY, json={"email": email, "challenge": challenge, "code": code})


def _wrong(code):
    return "00000000" if code != "00000000" else "11111111"


def test_code_login_issues_a_working_token(client, register_org, outbox):
    org, email = _user(register_org)
    r, challenge = _request(client, email)
    assert r.status_code == 202 and len(outbox) == 1 and outbox[0]["to"] == email
    code = _code(outbox)
    assert len(code) == 8 and code not in r.text and challenge
    tok = _verify(client, email, challenge, code).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["user"]["email"] == email and me["organization"]["id"] == org["organization"]["id"]


def test_code_is_single_use(client, register_org, outbox):
    _, email = _user(register_org)
    _r, challenge = _request(client, email); code = _code(outbox)
    assert _verify(client, email, challenge, code).status_code == 200
    assert _verify(client, email, challenge, code).status_code == 401


def test_a_code_needs_its_own_challenge(client, register_org, outbox):
    _, email = _user(register_org)
    _r, challenge = _request(client, email); code = _code(outbox)
    assert client.post(VERIFY, json={"email": email, "code": code}).status_code == 422          # no challenge
    assert _verify(client, email, str(uuid.uuid4()), code).status_code == 401                  # someone else's
    assert _verify(client, email, "not-a-challenge", code).status_code == 401
    assert _verify(client, email, challenge, code).status_code == 200


def test_an_attacker_without_the_challenge_cannot_burn_the_victims_code(client, register_org, outbox):
    # (i) Replaces the old "three wrong codes lock for one hour, then 24": wrong guesses without the victim's
    # challenge change nothing at all, however many there are.
    _, email = _user(register_org)
    _r, victim = _request(client, email); code = _code(outbox)
    for _ in range(10):
        assert _verify(client, email, str(uuid.uuid4()), _wrong(code)).status_code == 401
    assert _verify(client, email, victim, code).status_code == 200                             # was: 423


def test_the_victims_code_survives_requests_made_by_someone_else(client, register_org, outbox, db_session):
    # (ii) A new request no longer cancels the older codes (it used to supersede them).
    _, email = _user(register_org)
    _r, victim = _request(client, email); code = _code(outbox)
    for _ in range(4):
        # Under the old rule each request also waited 5 minutes; clearing that wait lets the old code supersede.
        db_session.execute(text("UPDATE login_code_throttles SET resend_available_at = NULL")); db_session.flush()
        assert client.post(REQUEST, json={"email": email}).status_code == 202
    assert _verify(client, email, victim, code).status_code == 200                             # was: 401


def test_a_fresh_code_is_never_refused_by_an_earlier_lock(client, register_org, outbox, db_session):
    # (iii) A 24-hour lock left by the old rule (lock_level 2, "contact support") is never read again.
    _, email = _user(register_org)
    client.post(REQUEST, json={"email": email})
    db_session.execute(text("UPDATE login_code_throttles SET locked_until = now() + interval '1 day', lock_level = 2, "
                            "resend_available_at = NULL"))
    db_session.flush()
    r, challenge = _request(client, email)
    assert r.status_code == 202                                                                 # was: 423
    assert _verify(client, email, challenge, _code(outbox)).status_code == 200                  # was: 423


def test_three_wrong_codes_cancel_that_code_only(client, register_org, outbox, db_session):
    # Replaces "[401, 401, 423] and even the right code is refused": three 401s, that one code is cancelled,
    # another live code of the same user still works, and the account is never locked.
    _, email = _user(register_org)
    _r, first = _request(client, email); first_code = _code(outbox)
    db_session.execute(text("UPDATE login_code_throttles SET resend_available_at = NULL")); db_session.flush()
    _r, second = _request(client, email); second_code = _code(outbox)
    assert [_verify(client, email, first, _wrong(first_code)).status_code for _ in range(3)] == [401, 401, 401]
    assert _verify(client, email, first, first_code).status_code == 401                         # cancelled
    assert _verify(client, email, second, second_code).status_code == 200


def test_a_sign_in_cancels_the_other_live_codes(client, register_org, outbox, db_session):
    _, email = _user(register_org)
    _r, first = _request(client, email); first_code = _code(outbox)
    db_session.execute(text("UPDATE login_code_throttles SET resend_available_at = NULL")); db_session.flush()
    _r, second = _request(client, email); second_code = _code(outbox)
    assert _verify(client, email, second, second_code).status_code == 200
    assert _verify(client, email, first, first_code).status_code == 401


def test_at_most_five_codes_per_address_per_hour(client, register_org, outbox, db_session):
    # Replaces "resend is blocked for five minutes": no per-address wait between codes, but the sixth code within
    # an hour is refused (429 with Retry-After) and no email is sent for it.
    _, email = _user(register_org)
    for _ in range(5):
        db_session.execute(text("UPDATE login_code_throttles SET resend_available_at = NULL")); db_session.flush()
        assert client.post(REQUEST, json={"email": email}).status_code == 202
    assert len(outbox) == 5
    # The old 5-minute wait is cleared here too, so against the old rule this sixth request is sent (unlimited).
    db_session.execute(text("UPDATE login_code_throttles SET resend_available_at = NULL")); db_session.flush()
    r = client.post(REQUEST, json={"email": email})
    assert r.status_code == 429 and 3500 <= int(r.headers["Retry-After"]) <= 3601 and len(outbox) == 5
    # An hour later the window has room again.
    db_session.execute(text("UPDATE login_codes SET created_at = created_at - interval '61 minutes'")); db_session.flush()
    assert client.post(REQUEST, json={"email": email}).status_code == 202 and len(outbox) == 6


def test_code_requests_use_their_own_per_ip_bucket(client, register_org, outbox, monkeypatch):
    from app.security import rate_limit

    calls = []
    real = rate_limit.check_rate_limit
    monkeypatch.setattr(rate_limit, "check_rate_limit", lambda **kw: (calls.append(kw), real(**kw))[1])
    _, email = _user(register_org)
    _r, challenge = _request(client, email)
    _verify(client, email, challenge, _code(outbox))
    buckets = [(c["installation_id"].split(":")[0], c["limit"]) for c in calls]
    assert [b for b in buckets if b[0].startswith("login-code")] == [("login-code-request-ip", 5), ("login-code-ip", 30)]


class _MemoryRedis:
    """Stands in for Redis in one test (the suite has none, so the limiter fails open everywhere else): the
    three calls check_rate_limit makes, on a dict. Swapped in through rate_limit._redis_client, the existing
    factory; no production code knows about it."""

    def __init__(self):
        self.counts = {}

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, seconds):
        return True

    def ttl(self, key):
        return 60


def test_the_sixth_code_request_from_one_ip_in_a_minute_is_refused(client, outbox, monkeypatch):
    from app.security import rate_limit

    memory = _MemoryRedis()
    monkeypatch.setattr(rate_limit, "_redis_client", lambda: memory)
    # Different addresses, so only the per-IP limit can refuse (was: one 30/min bucket shared with verifications).
    statuses = [client.post(REQUEST, json={"email": f"ip-{i}@example.com"}).status_code for i in range(6)]
    assert statuses == [202] * 5 + [429]
    assert client.post(VERIFY, json={"email": "ip-0@example.com", "challenge": str(uuid.uuid4()),
                                     "code": "12345678"}).status_code == 401      # verifications: their own bucket


def test_expired_code_is_rejected(client, register_org, outbox, db_session):
    _, email = _user(register_org)
    _r, challenge = _request(client, email); code = _code(outbox)
    db_session.execute(text("UPDATE login_codes SET expires_at = now() - interval '1 second'"))
    db_session.flush()
    assert _verify(client, email, challenge, code).status_code == 401


def test_unknown_email_is_indistinguishable_and_sends_nothing(client, register_org, outbox):
    _, email = _user(register_org)
    known = client.post(REQUEST, json={"email": email}).json()
    unknown = client.post(REQUEST, json={"email": "nobody@example.com"}).json()
    assert sorted(known) == sorted(unknown) and len(outbox) == 1
    uuid.UUID(unknown["challenge"])                                                             # looks the same
    assert _verify(client, "nobody@example.com", unknown["challenge"], "12345678").status_code == 401


def test_no_delivery_configured_means_no_code_and_honest_error(client, register_org, monkeypatch, db_session):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    _, email = _user(register_org)
    r = client.post(REQUEST, json={"email": email})
    assert r.status_code == 503
    assert db_session.execute(text("SELECT count(*) FROM login_codes")).scalar_one() == 0


def test_code_is_stored_only_as_a_keyed_hash(client, register_org, outbox, db_session):
    _, email = _user(register_org)
    client.post(REQUEST, json={"email": email}); code = _code(outbox)
    stored = db_session.execute(text("SELECT code_hash FROM login_codes")).scalars().all()
    assert stored and all(code not in h and len(h) == 64 for h in stored)


def test_code_for_one_user_does_not_open_another_account(client, register_org, outbox):
    _, email_a = _user(register_org)
    _, email_b = _user(register_org)
    _r, challenge_a = _request(client, email_a); code_a = _code(outbox)
    assert _verify(client, email_b, challenge_a, code_a).status_code == 401
