"""Wallet, reservations, payments and webhooks (ADR-104)."""
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import exc, text

from app.core.config import settings
from app.services import billing_service

W = "/api/v1/billing"
SECRET = "whsec_test_only_not_a_real_secret"


@pytest.fixture()
def sandbox(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "sandbox")
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SECRET", SecretStr(SECRET))


def _key():
    return f"idem-{uuid.uuid4().hex}"


def _hook(client, event, ts=None, secret=SECRET, provider="sandbox"):
    body = json.dumps(event).encode()
    ts = str(ts if ts is not None else int(time.time()))
    return client.post(f"{W}/webhooks/{provider}", content=body, headers={"Content-Type": "application/json",
                       "X-Webhook-Timestamp": ts, "X-Webhook-Signature": billing_service.sign(secret, ts, body)})


def _fund(client, org, cents):
    pay = client.post(f"{W}/payments", headers=org["headers"], json={"amount_cents": cents, "idempotency_key": _key()}).json()
    r = client.post(f"{W}/payments/{pay['id']}/sandbox-complete", headers=org["headers"]).json()
    assert r["status"] == "credited"
    return pay


def test_no_payment_provider_is_an_honest_blocked_state(client: TestClient, register_org, monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", None)
    org = register_org()
    w = client.get(f"{W}/wallet", headers=org["headers"]).json()
    assert w["payment_provider"]["status"] == "BLOCKED_EXTERNAL_DEPENDENCY" and w["balance_cents"] == 0
    r = client.post(f"{W}/payments", headers=org["headers"], json={"amount_cents": 500, "idempotency_key": _key()})
    assert r.status_code == 503


def test_payment_idempotency(client: TestClient, register_org, sandbox) -> None:
    org = register_org()
    key = _key()
    a = client.post(f"{W}/payments", headers=org["headers"], json={"amount_cents": 2500, "idempotency_key": key})
    b = client.post(f"{W}/payments", headers=org["headers"], json={"amount_cents": 2500, "idempotency_key": key})
    assert a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"] and b.json()["idempotent_replay"]
    assert client.post(f"{W}/payments", headers=org["headers"], json={"amount_cents": 9999, "idempotency_key": key}).status_code == 409
    assert client.get(f"{W}/payments", headers=org["headers"]).json()["total"] == 1


def test_webhook_credits_once_and_rejects_replays(client: TestClient, register_org, sandbox, db_session) -> None:
    org = register_org()
    pay = client.post(f"{W}/payments", headers=org["headers"], json={"amount_cents": 5000, "idempotency_key": _key()}).json()
    ppid = db_session.execute(text("SELECT provider_payment_id FROM payments WHERE id = :i"), {"i": pay["id"]}).scalar_one()
    evt = {"id": "evt_1", "type": "payment.succeeded", "data": {"provider_payment_id": ppid, "amount_cents": 5000, "currency": "USD"}}
    assert _hook(client, evt).json()["status"] == "credited"
    assert _hook(client, evt).json()["status"] == "duplicate_ignored"                      # same event replayed
    assert _hook(client, {**evt, "id": "evt_2"}).json()["status"] == "recorded"           # new id, payment already captured
    assert client.get(f"{W}/wallet", headers=org["headers"]).json()["available_cents"] == 5000   # credited exactly once
    assert _hook(client, {**evt, "id": "evt_3"}, ts=int(time.time()) - 3600).status_code == 400  # outside the window
    assert _hook(client, {**evt, "id": "evt_4"}, secret="wrong").status_code == 401             # forged signature
    r = client.post(f"{W}/webhooks/sandbox", content=b"{}", headers={"X-Webhook-Timestamp": str(int(time.time()))})
    assert r.status_code == 401                                                                 # unsigned


def test_webhook_amount_mismatch_never_credits(client: TestClient, register_org, sandbox, db_session) -> None:
    org = register_org()
    pay = client.post(f"{W}/payments", headers=org["headers"], json={"amount_cents": 5000, "idempotency_key": _key()}).json()
    ppid = db_session.execute(text("SELECT provider_payment_id FROM payments WHERE id = :i"), {"i": pay["id"]}).scalar_one()
    r = _hook(client, {"id": "evt_x", "type": "payment.succeeded", "data": {"provider_payment_id": ppid, "amount_cents": 999999, "currency": "USD"}})
    assert r.json()["status"] == "rejected_mismatch"
    assert client.get(f"{W}/wallet", headers=org["headers"]).json()["available_cents"] == 0


def test_reservation_and_settlement(client: TestClient, register_org, sandbox) -> None:
    org = register_org()
    _fund(client, org, 10_000)
    r = client.post(f"{W}/wallet/reservations", headers=org["headers"], json={"amount_cents": 3000, "reference": "ai-job:docs", "idempotency_key": _key()})
    assert r.status_code == 201
    res = r.json()
    w = client.get(f"{W}/wallet", headers=org["headers"]).json()
    assert (w["available_cents"], w["reserved_cents"], w["balance_cents"]) == (7000, 3000, 10_000)
    s = client.post(f"{W}/wallet/reservations/{res['id']}/settle", headers=org["headers"], json={"actual_cents": 1250}).json()
    assert s["status"] == "settled" and s["settled_cents"] == 1250
    w = client.get(f"{W}/wallet", headers=org["headers"]).json()
    assert (w["available_cents"], w["reserved_cents"], w["consumed_cents"]) == (8750, 0, 1250)       # unused hold returned
    again = client.post(f"{W}/wallet/reservations/{res['id']}/settle", headers=org["headers"], json={"actual_cents": 1250})
    assert again.status_code == 200 and client.get(f"{W}/wallet", headers=org["headers"]).json()["available_cents"] == 8750  # idempotent
    assert client.post(f"{W}/wallet/reservations/{res['id']}/settle", headers=org["headers"], json={"actual_cents": 999}).status_code == 409
    over = client.post(f"{W}/wallet/reservations", headers=org["headers"], json={"amount_cents": 100, "idempotency_key": _key()}).json()
    assert client.post(f"{W}/wallet/reservations/{over['id']}/settle", headers=org["headers"], json={"actual_cents": 101}).status_code == 422
    rel = client.post(f"{W}/wallet/reservations/{over['id']}/release", headers=org["headers"]).json()
    assert rel["status"] == "released" and client.get(f"{W}/wallet", headers=org["headers"]).json()["available_cents"] == 8750
    types = [e["entry_type"] for e in client.get(f"{W}/wallet/ledger?limit=50&sort_by=created_at&sort_dir=asc", headers=org["headers"]).json()["items"]]
    assert types == ["payment_captured", "reservation", "release", "ai_usage_charge", "reservation", "release"]


def test_insufficient_balance(client: TestClient, register_org, sandbox) -> None:
    org = register_org()
    _fund(client, org, 1000)
    client.post(f"{W}/wallet/reservations", headers=org["headers"], json={"amount_cents": 800, "idempotency_key": _key()})
    r = client.post(f"{W}/wallet/reservations", headers=org["headers"], json={"amount_cents": 300, "idempotency_key": _key()})
    assert r.status_code == 402 and "Insufficient" in r.text
    assert client.get(f"{W}/wallet", headers=org["headers"]).json()["available_cents"] == 200


def test_reservation_idempotency(client: TestClient, register_org, sandbox) -> None:
    org = register_org()
    _fund(client, org, 1000)
    key = _key()
    a = client.post(f"{W}/wallet/reservations", headers=org["headers"], json={"amount_cents": 400, "idempotency_key": key}).json()
    b = client.post(f"{W}/wallet/reservations", headers=org["headers"], json={"amount_cents": 400, "idempotency_key": key}).json()
    assert a["id"] == b["id"] and client.get(f"{W}/wallet", headers=org["headers"]).json()["available_cents"] == 600


def test_billing_is_tenant_isolated(client: TestClient, register_org, sandbox) -> None:
    a, b = register_org(), register_org()
    _fund(client, a, 5000)
    res = client.post(f"{W}/wallet/reservations", headers=a["headers"], json={"amount_cents": 1000, "idempotency_key": _key()}).json()
    assert client.get(f"{W}/wallet", headers=b["headers"]).json()["balance_cents"] == 0
    for path in ("/wallet/ledger", "/wallet/reservations", "/payments"):
        assert client.get(W + path, headers=b["headers"]).json()["total"] == 0
    assert client.post(f"{W}/wallet/reservations/{res['id']}/settle", headers=b["headers"], json={"actual_cents": 1}).status_code == 404
    assert client.post(f"{W}/wallet/reservations/{res['id']}/release", headers=b["headers"]).status_code == 404
    pay = client.get(f"{W}/payments", headers=a["headers"]).json()["items"][0]
    assert client.post(f"{W}/payments/{pay['id']}/sandbox-complete", headers=b["headers"]).status_code == 404


def test_money_moving_endpoints_need_an_admin(client: TestClient, register_org, sandbox) -> None:
    org = register_org()
    u = client.post("/api/v1/users", headers=org["headers"], json={"email": f"v{uuid.uuid4().hex[:6]}@x.example", "name": "Viewer",
                    "password": "viewer-pass-12345", "role": "viewer"})
    assert u.status_code in (200, 201), u.text
    tok = client.post("/api/v1/auth/login", data={"username": u.json()["email"], "password": "viewer-pass-12345"}).json()["access_token"]
    vh = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"{W}/wallet", headers=vh).status_code == 200
    assert client.post(f"{W}/payments", headers=vh, json={"amount_cents": 100, "idempotency_key": _key()}).status_code == 403
    assert client.post(f"{W}/wallet/reservations", headers=vh, json={"amount_cents": 100, "idempotency_key": _key()}).status_code == 403
    assert client.get(f"{W}/wallet").status_code == 401


def test_ledger_is_append_only(client: TestClient, register_org, sandbox, db_session) -> None:
    org = register_org()
    _fund(client, org, 1000)
    eid = client.get(f"{W}/wallet/ledger", headers=org["headers"]).json()["items"][0]["id"]
    with pytest.raises(exc.DBAPIError, match="append-only"):
        db_session.execute(text("UPDATE wallet_ledger_entries SET amount_cents = 999999 WHERE id = :i"), {"i": eid})
        db_session.flush()
    db_session.rollback()
    with pytest.raises(exc.DBAPIError, match="append-only"):
        db_session.execute(text("DELETE FROM wallet_ledger_entries WHERE id = :i"), {"i": eid})
        db_session.flush()
    db_session.rollback()
