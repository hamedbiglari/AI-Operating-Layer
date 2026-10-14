"""Email one-time login code — the owner's rules (see app/models/login_code.py)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import UserStatus
from app.models.login_code import LoginCode, LoginCodeThrottle
from app.models.user import User
from app.services import email_delivery
from app.services.audit import record_audit_log


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(code: str, user_id) -> str:  # noqa: ANN001
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


@dataclass
class Outcome:
    kind: str                     # sent | unknown | cooldown | locked | delivery_unavailable | ok | invalid
    retry_after_seconds: int | None = None
    locked_until: datetime | None = None
    contact_support: bool = False
    user: User | None = None


def _throttle(db: Session, user: User) -> LoginCodeThrottle:
    row = db.execute(select(LoginCodeThrottle).where(LoginCodeThrottle.user_id == user.id)
                     .with_for_update()).scalar_one_or_none()
    if row is None:
        row = LoginCodeThrottle(user_id=user.id, organization_id=user.organization_id, failed_attempts=0, lock_level=0)
        db.add(row)
        db.flush()
    return row


def _locked(th: LoginCodeThrottle, now: datetime) -> Outcome | None:
    if th.locked_until and th.locked_until > now:
        return Outcome("locked", locked_until=th.locked_until, contact_support=th.lock_level >= 2,
                       retry_after_seconds=int((th.locked_until - now).total_seconds()))
    return None


def _user(db: Session, email: str) -> User | None:
    user = db.execute(select(User).where(func.lower(User.email) == email.strip().lower())).scalar_one_or_none()
    return user if user is not None and user.status == UserStatus.ACTIVE else None


def request_code(db: Session, *, email: str) -> Outcome:
    # Checked before the account lookup so the answer never depends on
    # whether the address exists.
    if not email_delivery.is_configured():
        return Outcome("delivery_unavailable")
    user = _user(db, email)
    if user is None:
        # Same outward answer as "sent" (no account enumeration); nothing is created or sent.
        return Outcome("unknown")
    now = _now()
    th = _throttle(db, user)
    if (locked := _locked(th, now)) is not None:
        db.commit()
        return locked
    if th.resend_available_at and th.resend_available_at > now:
        db.commit()
        return Outcome("cooldown", retry_after_seconds=int((th.resend_available_at - now).total_seconds()) + 1)
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.execute(update(LoginCode).where(LoginCode.user_id == user.id, LoginCode.consumed_at.is_(None))
               .values(consumed_at=now))  # a new code supersedes older ones
    db.add(LoginCode(user_id=user.id, organization_id=user.organization_id, code_hash=_hash(code, user.id),
                     expires_at=now + timedelta(seconds=settings.LOGIN_CODE_TTL_SECONDS)))
    th.resend_available_at = now + timedelta(seconds=settings.LOGIN_CODE_RESEND_SECONDS)
    try:
        email_delivery.send(to=user.email, subject=f"{settings.APP_NAME} sign-in code",
                            body=f"Your sign-in code is {code}. It expires in "
                                 f"{settings.LOGIN_CODE_TTL_SECONDS // 60} minutes.")
    except email_delivery.DeliveryFailed:
        db.rollback()
        return Outcome("delivery_unavailable")
    db.commit()
    return Outcome("sent", retry_after_seconds=settings.LOGIN_CODE_RESEND_SECONDS)


def verify_code(db: Session, *, email: str, code: str) -> Outcome:
    user = _user(db, email)
    if user is None:
        return Outcome("invalid")
    now = _now()
    th = _throttle(db, user)
    if (locked := _locked(th, now)) is not None:
        db.commit()
        return locked
    row = db.execute(select(LoginCode).where(
        LoginCode.user_id == user.id, LoginCode.consumed_at.is_(None), LoginCode.expires_at > now,
    ).order_by(LoginCode.created_at.desc()).limit(1)).scalar_one_or_none()
    good = row is not None and code.isdigit() and len(code) == 6 and \
        hmac.compare_digest(row.code_hash, _hash(code, user.id))
    if good:
        row.consumed_at = now
        th.failed_attempts, th.lock_level, th.locked_until = 0, 0, None
        record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="auth.login_code",
                         resource_type="user", resource_id=user.id)
        db.commit()
        return Outcome("ok", user=user)
    th.failed_attempts += 1
    if th.failed_attempts >= settings.LOGIN_CODE_MAX_FAILURES:
        th.failed_attempts = 0
        th.lock_level = min(th.lock_level + 1, 2)
        seconds = settings.LOGIN_CODE_FIRST_LOCK_SECONDS if th.lock_level == 1 else settings.LOGIN_CODE_SECOND_LOCK_SECONDS
        th.locked_until = now + timedelta(seconds=seconds)
        db.commit()
        return Outcome("locked", locked_until=th.locked_until, contact_support=th.lock_level >= 2,
                       retry_after_seconds=seconds)
    db.commit()
    return Outcome("invalid")
