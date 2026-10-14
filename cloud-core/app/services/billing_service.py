"""
Wallet / ledger / reservations / payments (ADR-104, following ADR-084/086).

  available = sum(ledger amounts)            (reservations move money out of `available`)
  reserved  = sum(amount of HELD reservations)
  consumed  = -sum(ai_usage_charge entries)
Every financial event is one immutable ledger row with a unique idempotency key, so a retried
request or a replayed webhook can never move money twice.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.billing_wallet import Payment, PaymentWebhookEvent, Wallet, WalletLedgerEntry, WalletReservation

MAX_AMOUNT_CENTS = 10_000_000   # 100 000.00 per operation


def _now() -> datetime:
    return datetime.now(timezone.utc)


def wallet(db: Session, organization_id: UUID, *, lock: bool = False) -> Wallet:
    q = select(Wallet).where(Wallet.organization_id == organization_id)
    w = db.execute(q.with_for_update() if lock else q).scalar_one_or_none()
    if w is None:
        w = Wallet(organization_id=organization_id, currency=settings.WALLET_CURRENCY)
        db.add(w)
        db.flush()
        if lock:
            w = db.execute(q.with_for_update()).scalar_one()
    return w


def balances(db: Session, w: Wallet) -> dict:
    available = db.execute(select(func.coalesce(func.sum(WalletLedgerEntry.amount_cents), 0))
                           .where(WalletLedgerEntry.wallet_id == w.id)).scalar_one()
    reserved = db.execute(select(func.coalesce(func.sum(WalletReservation.amount_cents), 0))
                          .where(WalletReservation.wallet_id == w.id, WalletReservation.status == "held")).scalar_one()
    consumed = -db.execute(select(func.coalesce(func.sum(WalletLedgerEntry.amount_cents), 0))
                           .where(WalletLedgerEntry.wallet_id == w.id, WalletLedgerEntry.entry_type == "ai_usage_charge")).scalar_one()
    return {"currency": w.currency, "available_cents": int(available), "reserved_cents": int(reserved),
            "consumed_cents": int(consumed), "balance_cents": int(available) + int(reserved)}


def _entry(db: Session, w: Wallet, entry_type: str, amount: int, key: str, **kw) -> WalletLedgerEntry:
    e = WalletLedgerEntry(organization_id=w.organization_id, wallet_id=w.id, entry_type=entry_type, amount_cents=amount,
                          idempotency_key=key, **kw)
    db.add(e)
    return e


def _amount(v: int) -> int:
    if not isinstance(v, int) or v <= 0 or v > MAX_AMOUNT_CENTS:
        raise HTTPException(422, f"amount must be an integer number of cents between 1 and {MAX_AMOUNT_CENTS}.")
    return v


# ---------------------------------------------------------------- reservations
def reserve(db: Session, *, organization_id: UUID, amount_cents: int, reference: str | None, idempotency_key: str) -> WalletReservation:
    _amount(amount_cents)
    w = wallet(db, organization_id, lock=True)       # serialises concurrent reservations for this tenant
    existing = db.execute(select(WalletReservation).where(WalletReservation.organization_id == organization_id,
                                                          WalletReservation.idempotency_key == idempotency_key)).scalar_one_or_none()
    if existing:
        if existing.amount_cents != amount_cents:
            raise HTTPException(409, "This idempotency key was already used with a different amount.")
        db.rollback()
        return existing
    if balances(db, w)["available_cents"] < amount_cents:
        db.rollback()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Insufficient wallet balance for this reservation.")
    r = WalletReservation(organization_id=organization_id, wallet_id=w.id, amount_cents=amount_cents, status="held",
                          reference=reference, idempotency_key=idempotency_key)
    db.add(r)
    db.flush()
    _entry(db, w, "reservation", -amount_cents, f"res:{r.id}", reservation_id=r.id, reference=reference)
    db.commit()
    db.refresh(r)
    return r


def _reservation(db: Session, organization_id: UUID, reservation_id: UUID) -> WalletReservation:
    wallet(db, organization_id, lock=True)
    r = db.execute(select(WalletReservation).where(WalletReservation.id == reservation_id,
                                                   WalletReservation.organization_id == organization_id).with_for_update()).scalar_one_or_none()
    if r is None:
        db.rollback()
        raise HTTPException(404, "Reservation not found.")
    return r


def settle(db: Session, *, organization_id: UUID, reservation_id: UUID, actual_cents: int) -> WalletReservation:
    if not isinstance(actual_cents, int) or actual_cents < 0:
        raise HTTPException(422, "actual_cents must be a non-negative integer.")
    r = _reservation(db, organization_id, reservation_id)
    if r.status == "settled":
        if r.settled_cents != actual_cents:
            db.rollback()
            raise HTTPException(409, "Reservation already settled with a different amount.")
        db.rollback()
        return r
    if r.status != "held":
        db.rollback()
        raise HTTPException(409, f"Reservation is {r.status}; only a held reservation can be settled.")
    if actual_cents > r.amount_cents:
        db.rollback()
        raise HTTPException(422, "Actual cost exceeds the reserved amount.")
    w = db.get(Wallet, r.wallet_id)
    _entry(db, w, "release", r.amount_cents, f"rel:{r.id}", reservation_id=r.id, reference=r.reference, note="hold closed at settlement")
    if actual_cents:
        _entry(db, w, "ai_usage_charge", -actual_cents, f"chg:{r.id}", reservation_id=r.id, reference=r.reference)
    r.status, r.settled_cents, r.closed_at = "settled", actual_cents, _now()
    db.commit()
    db.refresh(r)
    return r


def release(db: Session, *, organization_id: UUID, reservation_id: UUID) -> WalletReservation:
    r = _reservation(db, organization_id, reservation_id)
    if r.status == "released":
        db.rollback()
        return r
    if r.status != "held":
        db.rollback()
        raise HTTPException(409, f"Reservation is {r.status}; only a held reservation can be released.")
    _entry(db, db.get(Wallet, r.wallet_id), "release", r.amount_cents, f"rel:{r.id}", reservation_id=r.id, reference=r.reference)
    r.status, r.closed_at = "released", _now()
    db.commit()
    db.refresh(r)
    return r


# ---------------------------------------------------------------- payments + webhooks
def provider_status() -> dict:
    p = settings.PAYMENT_PROVIDER
    if not p:
        return {"provider": None, "status": "BLOCKED_EXTERNAL_DEPENDENCY",
                "detail": "No payment provider is configured; wallet top-ups are unavailable."}
    if p == "sandbox":
        return {"provider": "sandbox", "status": "SANDBOX", "detail": "Development sandbox — no real money moves."}
    return {"provider": p, "status": "BLOCKED_EXTERNAL_DEPENDENCY",
            "detail": f"Payment provider '{p}' has no adapter in this build."}


def create_payment(db: Session, *, organization_id: UUID, amount_cents: int, idempotency_key: str) -> tuple[Payment, bool]:
    _amount(amount_cents)
    if settings.PAYMENT_PROVIDER != "sandbox":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, provider_status()["detail"])
    existing = db.execute(select(Payment).where(Payment.organization_id == organization_id,
                                                Payment.idempotency_key == idempotency_key)).scalar_one_or_none()
    if existing:
        if existing.amount_cents != amount_cents:
            raise HTTPException(409, "This idempotency key was already used with a different amount.")
        return existing, False
    w = wallet(db, organization_id)
    pay = Payment(organization_id=organization_id, wallet_id=w.id, provider="sandbox", provider_payment_id=f"sbx_{uuid.uuid4().hex}",
                  amount_cents=amount_cents, currency=w.currency, status="pending", idempotency_key=idempotency_key)
    db.add(pay)
    db.commit()
    db.refresh(pay)
    return pay, True


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def handle_webhook(db: Session, *, provider: str, body: bytes, signature: str | None, timestamp: str | None) -> dict:
    if provider != settings.PAYMENT_PROVIDER or settings.PAYMENT_WEBHOOK_SECRET is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhooks for this provider are not configured.")
    if not signature or not timestamp or not timestamp.isdigit():
        raise HTTPException(401, "Missing webhook signature.")
    if abs(time.time() - int(timestamp)) > settings.PAYMENT_WEBHOOK_TOLERANCE_SECONDS:
        raise HTTPException(400, "Webhook timestamp outside the accepted window (possible replay).")
    expected = sign(settings.PAYMENT_WEBHOOK_SECRET.get_secret_value(), timestamp, body)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid webhook signature.")
    try:
        evt = json.loads(body)
        event_id, event_type = str(evt["id"]), str(evt["type"])
        data = evt.get("data") or {}
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Malformed webhook payload.") from None
    if db.execute(select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider == provider,
                                                    PaymentWebhookEvent.event_id == event_id)).scalar_one_or_none():
        return {"status": "duplicate_ignored", "event_id": event_id}
    pay = db.execute(select(Payment).where(Payment.provider == provider,
                                           Payment.provider_payment_id == str(data.get("provider_payment_id", ""))).with_for_update()).scalar_one_or_none()
    db.add(PaymentWebhookEvent(organization_id=pay.organization_id if pay else None, provider=provider, event_id=event_id,
                               event_type=event_type, payment_id=pay.id if pay else None, payload=evt))
    outcome = "recorded"
    if pay is not None and event_type == "payment.succeeded" and pay.status == "pending":
        if int(data.get("amount_cents", -1)) != pay.amount_cents or data.get("currency") != pay.currency:
            pay.status, pay.failure_reason = "failed", "amount or currency mismatch in provider event"
            outcome = "rejected_mismatch"
        else:
            pay.status = "succeeded"
            _entry(db, db.get(Wallet, pay.wallet_id), "payment_captured", pay.amount_cents, f"pay:{pay.id}", payment_id=pay.id,
                   reference=pay.provider_payment_id)
            outcome = "credited"
    elif pay is not None and event_type == "payment.failed" and pay.status == "pending":
        pay.status, pay.failure_reason = "failed", str(data.get("reason", "provider reported failure"))[:500]
        outcome = "failed"
    db.commit()
    return {"status": outcome, "event_id": event_id}


def sandbox_complete(db: Session, *, organization_id: UUID, payment_id: UUID) -> dict:
    """Development only: emits the provider's success event through the SAME signed webhook path."""
    if settings.PAYMENT_PROVIDER != "sandbox" or settings.PAYMENT_WEBHOOK_SECRET is None:
        raise HTTPException(404, "Not available.")
    pay = db.execute(select(Payment).where(Payment.id == payment_id, Payment.organization_id == organization_id)).scalar_one_or_none()
    if pay is None:
        raise HTTPException(404, "Payment not found.")
    body = json.dumps({"id": f"evt_{uuid.uuid4().hex}", "type": "payment.succeeded",
                       "data": {"provider_payment_id": pay.provider_payment_id, "amount_cents": pay.amount_cents, "currency": pay.currency}}).encode()
    ts = str(int(time.time()))
    return handle_webhook(db, provider="sandbox", body=body, signature=sign(settings.PAYMENT_WEBHOOK_SECRET.get_secret_value(), ts, body), timestamp=ts)
