"""Wallet / payments API (ADR-104). Tenant-scoped; money-moving writes need OWNER or ADMIN."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.billing_wallet import Payment, WalletLedgerEntry, WalletReservation
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import billing_service as svc

router = APIRouter(prefix="/billing", tags=["billing"])
Admin = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))
Reader = Depends(get_current_user)


class ReserveIn(BaseModel):
    amount_cents: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=300)
    idempotency_key: str = Field(min_length=8, max_length=200)


class SettleIn(BaseModel):
    actual_cents: int = Field(ge=0)


class PaymentIn(BaseModel):
    amount_cents: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=200)


def _res(r: WalletReservation) -> dict:
    return {k: getattr(r, k) for k in ("id", "amount_cents", "settled_cents", "status", "reference", "created_at", "closed_at")}


def _pay(p: Payment) -> dict:
    return {k: getattr(p, k) for k in ("id", "provider", "amount_cents", "currency", "status", "failure_reason", "created_at", "updated_at")}


@router.get("/wallet")
def get_wallet(user: User = Reader, db: Session = Depends(get_db)) -> dict:
    w = svc.wallet(db, user.organization_id)
    db.commit()
    return {**svc.balances(db, w), "payment_provider": svc.provider_status()}


def _page(db, stmt, model, p, sort, default):  # noqa: ANN001, ANN202
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, model, sort, default_field=default, default_dir=SortDirection.DESC)
    return total, db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()


@router.get("/usage")
def usage(user: User = Reader, db: Session = Depends(get_db)) -> dict:
    """Credit, AI-account quotas, the visibility budget and this month's tokens, each measured against the
    limit that enforces it (ADR-127). Money amounts on AI accounts are shown to owners and admins only."""
    from app.models.user_preferences import UserPreferences

    pref = db.execute(select(UserPreferences).where(UserPreferences.organization_id == user.organization_id,
                                                    UserPreferences.user_id == user.id)).scalar_one_or_none()
    threshold = ((pref.usage_alert_threshold if pref else None) or 80) / 100
    out = svc.usage_summary(db, user.organization_id, show_costs=user.role in (UserRole.OWNER, UserRole.ADMIN),
                            threshold=threshold)
    db.commit()            # the wallet row may have just been created
    return out


@router.get("/wallet/ledger", response_model=Page[dict])
def ledger(p: PaginationParams = Depends(), sort: SortParams = Depends(), user: User = Reader, db: Session = Depends(get_db)):
    total, rows = _page(db, select(WalletLedgerEntry).where(WalletLedgerEntry.organization_id == user.organization_id),
                        WalletLedgerEntry, p, sort, "created_at")
    return Page(items=[{k: getattr(e, k) for k in ("id", "entry_type", "amount_cents", "reservation_id", "payment_id", "reference", "created_at")} for e in rows],
                total=total, limit=p.limit, offset=p.offset)


@router.get("/wallet/reservations", response_model=Page[dict])
def reservations(p: PaginationParams = Depends(), sort: SortParams = Depends(), user: User = Reader, db: Session = Depends(get_db)):
    total, rows = _page(db, select(WalletReservation).where(WalletReservation.organization_id == user.organization_id),
                        WalletReservation, p, sort, "created_at")
    return Page(items=[_res(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/wallet/reservations", status_code=201)
def reserve(body: ReserveIn, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return _res(svc.reserve(db, organization_id=user.organization_id, amount_cents=body.amount_cents,
                            reference=body.reference, idempotency_key=body.idempotency_key))


@router.post("/wallet/reservations/{reservation_id}/settle")
def settle(reservation_id: UUID, body: SettleIn, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return _res(svc.settle(db, organization_id=user.organization_id, reservation_id=reservation_id, actual_cents=body.actual_cents))


@router.post("/wallet/reservations/{reservation_id}/release")
def release(reservation_id: UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return _res(svc.release(db, organization_id=user.organization_id, reservation_id=reservation_id))


@router.get("/payments", response_model=Page[dict])
def payments(p: PaginationParams = Depends(), sort: SortParams = Depends(), user: User = Reader, db: Session = Depends(get_db)):
    total, rows = _page(db, select(Payment).where(Payment.organization_id == user.organization_id), Payment, p, sort, "created_at")
    return Page(items=[_pay(x) for x in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/payments", status_code=201)
def create_payment(body: PaymentIn, response: Response, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    pay, created = svc.create_payment(db, organization_id=user.organization_id, amount_cents=body.amount_cents,
                                      idempotency_key=body.idempotency_key)
    if not created:
        response.status_code = 200
    return {**_pay(pay), "idempotent_replay": not created}


@router.post("/payments/{payment_id}/sandbox-complete")
def sandbox_complete(payment_id: UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return svc.sandbox_complete(db, organization_id=user.organization_id, payment_id=payment_id)


@router.post("/webhooks/{provider}")
async def webhook(provider: str, request: Request, db: Session = Depends(get_db),
                  x_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
                  x_timestamp: str | None = Header(default=None, alias="X-Webhook-Timestamp")) -> dict:
    body = await request.body()
    if len(body) > 64 * 1024:
        from fastapi import HTTPException
        raise HTTPException(413, "Payload too large.")
    return svc.handle_webhook(db, provider=provider, body=body, signature=x_signature, timestamp=x_timestamp)
