"""Confirmed change of the signed-in user's own sign-in email (V5-self-email-verification).

request() emails a 6-digit code to the NEW address; verify() applies the change only when that code is entered.
Same rules as the login code where they apply: the code lives LOGIN_CODE_TTL_SECONDS, the same address can be asked
for again after LOGIN_CODE_RESEND_SECONDS, LOGIN_CODE_MAX_FAILURES wrong codes void the request. A user may start at
most MAX_REQUESTS_PER_HOUR requests an hour, so the endpoint cannot be used to mail-bomb arbitrary addresses. With no
SMTP configured nothing is created and the caller is told so (no fake "sent"). After a change the OLD address is told,
best effort, so an owner whose session was misused learns about it.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_change import EmailChangeRequest
from app.models.user import User
from app.services import email_delivery
from app.services.audit import record_audit_log

MAX_REQUESTS_PER_HOUR = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(code: str, user_id, new_email: str) -> str:  # noqa: ANN001
    return hmac.new(settings.SECRET_KEY.encode(), f"email-change:{user_id}:{new_email}:{code}".encode(),
                    hashlib.sha256).hexdigest()


@dataclass
class Outcome:
    kind: str     # sent | same | taken | cooldown | too_many_requests | delivery_unavailable | ok | invalid | none | voided
    retry_after_seconds: int | None = None
    user: User | None = None


def _taken(db: Session, email: str, user: User) -> bool:
    return db.execute(select(func.count()).select_from(User).where(
        func.lower(User.email) == email, User.id != user.id)).scalar_one() > 0


def request(db: Session, *, user: User, new_email: str) -> Outcome:
    new = new_email.strip().lower()
    if new == user.email.lower():
        return Outcome("same")
    if _taken(db, new, user):
        return Outcome("taken")
    if not email_delivery.is_configured():
        return Outcome("delivery_unavailable")
    now = _now()
    recent = db.execute(select(EmailChangeRequest).where(
        EmailChangeRequest.user_id == user.id, EmailChangeRequest.created_at > now - timedelta(hours=1),
    ).order_by(EmailChangeRequest.created_at.desc())).scalars().all()
    if len(recent) >= MAX_REQUESTS_PER_HOUR:
        oldest = min(r.created_at for r in recent)
        return Outcome("too_many_requests", retry_after_seconds=int((oldest + timedelta(hours=1) - now).total_seconds()) + 1)
    same = next((r for r in recent if r.new_email == new and r.consumed_at is None), None)
    if same is not None and same.created_at > now - timedelta(seconds=settings.LOGIN_CODE_RESEND_SECONDS):
        wait = same.created_at + timedelta(seconds=settings.LOGIN_CODE_RESEND_SECONDS) - now
        return Outcome("cooldown", retry_after_seconds=int(wait.total_seconds()) + 1)
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.execute(update(EmailChangeRequest).where(EmailChangeRequest.user_id == user.id,
                                                EmailChangeRequest.consumed_at.is_(None)).values(consumed_at=now))
    db.add(EmailChangeRequest(user_id=user.id, organization_id=user.organization_id, new_email=new,
                              code_hash=_hash(code, user.id, new),
                              expires_at=now + timedelta(seconds=settings.LOGIN_CODE_TTL_SECONDS)))
    record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="user.email_change_requested",
                     resource_type="user", resource_id=user.id, new_value={"new_email": new})
    try:
        email_delivery.send(to=new, subject=f"{settings.APP_NAME}: confirm your new email address",
                            body=f"Your confirmation code is {code}. Enter it in Settings to make {new} your sign-in "
                                 f"address. It expires in {settings.LOGIN_CODE_TTL_SECONDS // 60} minutes. If you did not "
                                 f"ask for this, ignore this message: nothing changes.")
    except (email_delivery.DeliveryFailed, email_delivery.DeliveryNotConfigured):
        db.rollback()
        return Outcome("delivery_unavailable")
    db.commit()
    return Outcome("sent", retry_after_seconds=settings.LOGIN_CODE_RESEND_SECONDS)


def verify(db: Session, *, user: User, code: str) -> Outcome:
    now = _now()
    row = db.execute(select(EmailChangeRequest).where(
        EmailChangeRequest.user_id == user.id, EmailChangeRequest.consumed_at.is_(None),
        EmailChangeRequest.expires_at > now,
    ).order_by(EmailChangeRequest.created_at.desc()).limit(1).with_for_update()).scalar_one_or_none()
    if row is None:
        return Outcome("none")
    good = code.isdigit() and len(code) == 6 and hmac.compare_digest(row.code_hash, _hash(code, user.id, row.new_email))
    if not good:
        row.failed_attempts += 1
        if row.failed_attempts >= settings.LOGIN_CODE_MAX_FAILURES:
            row.consumed_at = now
            db.commit()
            return Outcome("voided")
        db.commit()
        return Outcome("invalid")
    old = user.email
    if _taken(db, row.new_email, user):
        row.consumed_at = now
        db.commit()
        return Outcome("taken")
    row.consumed_at = now
    user.email = row.new_email
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return Outcome("taken")
    record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="user.email_changed",
                     resource_type="user", resource_id=user.id, old_value={"email": old}, new_value={"email": user.email})
    db.commit()
    db.refresh(user)
    try:
        email_delivery.send(to=old, subject=f"{settings.APP_NAME}: your sign-in email was changed",
                            body=f"The sign-in address of your account was changed from {old} to {user.email}. "
                                 f"If you did not do this, contact support at once.")
    except (email_delivery.DeliveryFailed, email_delivery.DeliveryNotConfigured):
        pass  # the change is confirmed by the new address; this notice is best effort
    return Outcome("ok", user=user)
