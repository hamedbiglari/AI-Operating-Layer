"""Usage & quota summary (ADR-127): one view of credit, AI-account spend limits, the visibility budget and this
month's tokens — each measured against the record that enforces it."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core.config import settings
from app.models.ai_center import AIProviderAccount
from app.services import billing_service

B = "/api/v1/ai-center"


@pytest.fixture(autouse=True)
def _cred_key(monkeypatch):
    monkeypatch.setattr(settings, "AI_CREDENTIAL_KEY", SecretStr(Fernet.generate_key().decode()))


def _account(client, h, label="Main", spend_limit=None, db=None):
    p = client.post(f"{B}/providers", headers=h, json={"name": f"P-{uuid.uuid4().hex[:5]}", "adapter_key": "anthropic",
                                                       "official_url": "https://example.com"}).json()
    a = client.post(f"{B}/accounts", headers=h, json={"provider_id": p["id"], "label": label}).json()
    if spend_limit is not None:
        row = db.get(AIProviderAccount, uuid.UUID(a["id"]))
        row.spend_limit, row.spend_limit_currency = spend_limit, "USD"
        db.commit()
    return a


def test_a_new_organisation_sees_every_quota_as_not_configured_never_as_zero_percent(client, register_org):
    org = register_org()
    r = client.get("/api/v1/billing/usage", headers=org["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    by_key = {q["key"]: q for q in body["quotas"]}
    assert by_key["wallet"]["state"] == "not_configured" and by_key["wallet"]["percent"] is None
    assert by_key["visibility"]["state"] == "not_configured"
    assert body["nudge"] is None
    assert body["tokens"]["requests"] == 0 and body["tokens"]["input_tokens"] is None   # unknown, not 0
    assert all(q["at_limit"] for q in body["quotas"])                                   # behaviour is stated


def test_the_meter_uses_the_same_monthly_spend_the_router_enforces_and_nudges_at_80_percent(
        client, db_session, register_org, monkeypatch):
    org = register_org()
    h = org["headers"]
    a = _account(client, h, "Main", spend_limit=10, db=db_session)
    from app.services import ai_routing_service

    monkeypatch.setattr(ai_routing_service, "_month_spend", lambda db, acc: Decimal("8.4"))
    body = client.get("/api/v1/billing/usage", headers=h).json()
    q = next(x for x in body["quotas"] if x["key"] == f"ai_account:{a['id']}")
    assert q["used"] == 8.4 and q["limit"] == 10 and q["percent"] == 0.84 and q["state"] == "warning"
    assert q["resets_at"] and "SPEND_LIMIT" in q["at_limit"]
    assert body["nudge"]["key"] == q["key"]


def test_wallet_share_counts_consumed_and_held_credit(client, db_session, register_org):
    org = register_org()
    oid = uuid.UUID(org["organization"]["id"])
    w = billing_service.wallet(db_session, oid)
    billing_service._entry(db_session, w, "credit_granted", 10000, f"t-{uuid.uuid4().hex}")            # 100.00 credited
    billing_service._entry(db_session, w, "ai_usage_charge", -7000, f"t-{uuid.uuid4().hex}")  # 70.00 used
    db_session.commit()
    body = client.get("/api/v1/billing/usage", headers=org["headers"]).json()
    q = next(x for x in body["quotas"] if x["key"] == "wallet")
    assert q["used"] == 70.0 and q["limit"] == 100.0 and q["percent"] == 0.7 and q["state"] == "ok"
    assert "30.00" in q["detail"]


def test_viewers_see_the_share_but_not_the_ai_account_amounts(client, db_session, register_org, monkeypatch):
    org = register_org()
    h = org["headers"]
    a = _account(client, h, "Main", spend_limit=10, db=db_session)
    from app.services import ai_routing_service

    monkeypatch.setattr(ai_routing_service, "_month_spend", lambda db, acc: Decimal("5"))
    email = f"v-{uuid.uuid4().hex[:6]}@example.dev"
    client.post("/api/v1/users", headers=h, json={"email": email, "name": "V", "password": "supersecret123",
                                                  "role": "viewer"})
    tok = client.post("/api/v1/auth/login", data={"username": email, "password": "supersecret123"}).json()["access_token"]
    body = client.get("/api/v1/billing/usage", headers={"Authorization": f"Bearer {tok}"}).json()
    q = next(x for x in body["quotas"] if x["key"] == f"ai_account:{a['id']}")
    assert q["used"] is None and q["limit"] is None and q["percent"] == 0.5
    assert body["tokens"]["estimated_cost"] is None


def test_usage_is_tenant_scoped(client, db_session, register_org, monkeypatch):
    a_org, b_org = register_org(), register_org()
    a = _account(client, a_org["headers"], "Secret account", spend_limit=10, db=db_session)
    body = client.get("/api/v1/billing/usage", headers=b_org["headers"]).json()
    assert all(a["id"] not in q["key"] and "Secret account" not in q["label"] for q in body["quotas"])


def test_moving_credit_on_and_off_hold_is_not_counted_as_new_credit(client, db_session, register_org):
    org = register_org()
    oid = uuid.UUID(org["organization"]["id"])
    w = billing_service.wallet(db_session, oid)
    billing_service._entry(db_session, w, "credit_granted", 5000, f"t-{uuid.uuid4().hex}")
    billing_service._entry(db_session, w, "reservation", -2000, f"t-{uuid.uuid4().hex}")
    billing_service._entry(db_session, w, "release", 2000, f"t-{uuid.uuid4().hex}")
    db_session.commit()
    q = next(x for x in client.get("/api/v1/billing/usage", headers=org["headers"]).json()["quotas"] if x["key"] == "wallet")
    assert q["limit"] == 50.0 and q["used"] == 0.0


def test_the_nudge_threshold_is_the_users_own_saved_setting(client, db_session, register_org, monkeypatch):
    org = register_org()
    h = org["headers"]
    a = _account(client, h, "Main", spend_limit=10, db=db_session)
    from app.services import ai_routing_service

    monkeypatch.setattr(ai_routing_service, "_month_spend", lambda db, acc: Decimal("7"))     # 70 %
    assert client.get("/api/v1/billing/usage", headers=h).json()["nudge"] is None             # default 80 %
    r = client.put("/api/v1/users/me/preferences", headers=h, json={"usage_alert_threshold": 60})
    assert r.status_code == 200 and r.json()["usage_alert_threshold"] == 60
    body = client.get("/api/v1/billing/usage", headers=h).json()
    assert body["threshold"] == 0.6 and body["nudge"]["key"] == f"ai_account:{a['id']}"
    for bad in (10, 101):
        assert client.put("/api/v1/users/me/preferences", headers=h, json={"usage_alert_threshold": bad}).status_code == 422
