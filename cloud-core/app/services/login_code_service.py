"""Email one-time login code (see app/models/login_code.py), as changed by SEC-login-code-lockout (option B):

- every request creates its own 8-digit code, bound to a challenge (the code row's random id) that only the
  requester receives; a new request never cancels another code;
- a code is accepted only with its own challenge; wrong guesses count against that one code, and
  LOGIN_CODE_MAX_FAILURES of them cancel it; nothing ever locks the account;
- at most LOGIN_CODE_MAX_PER_HOUR codes are sent per address per rolling hour (no email above it);
- a sign-in cancels the user's other live codes.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
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

CODE_DIGITS = 8
_WINDOW = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(code: str, user_id) -> str:  # noqa: ANN001
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


@dataclass
class Outcome:
    kind: str                     # sent | unknown | rate_limited | delivery_unavailable | ok | invalid
    challenge: str | None = None
    retry_after_seconds: int | None = None
    user: User | None = None


def _serialize(db: Session, user: User) -> None:
    """Holds the user's throttle row for this transaction so two requests cannot both pass the hourly count.
    The row's own columns (failed_attempts, lock_level, locked_until, resend_available_at) are no longer used."""
    row = db.execute(select(LoginCodeThrottle).where(LoginCodeThrottle.user_id == user.id)
                     .with_for_update()).scalar_one_or_none()
    if row is None:
        db.add(LoginCodeThrottle(user_id=user.id, organization_id=user.organization_id))
        db.flush()


def _user(db: Session, email: str) -> User | None:
    user = db.execute(select(User).where(func.lower(User.email) == email.strip().lower())).scalar_one_or_none()
    # A deleted user (V5-admin-trash) is treated like an unknown address: no code, the same answer.
    return user if user is not None and user.status == UserStatus.ACTIVE and user.deleted_at is None else None


def request_code(db: Session, *, email: str) -> Outcome:
    # Checked before the account lookup so the answer never depends on
    # whether the address exists.
    if not email_delivery.is_configured():
        return Outcome("delivery_unavailable")
    user = _user(db, email)
    if user is None:
        # Same outward answer as "sent", with a challenge that leads nowhere; nothing is created or sent.
        return Outcome("unknown", challenge=str(uuid.uuid4()))
    now = _now()
    _serialize(db, user)
    recent = db.execute(select(LoginCode.created_at).where(
        LoginCode.user_id == user.id, LoginCode.created_at > now - _WINDOW,
    ).order_by(LoginCode.created_at)).scalars().all()
    if len(recent) >= settings.LOGIN_CODE_MAX_PER_HOUR:
        db.commit()
        return Outcome("rate_limited", retry_after_seconds=int((recent[0] + _WINDOW - now).total_seconds()) + 1)
    code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
    row = LoginCode(id=uuid.uuid4(), user_id=user.id, organization_id=user.organization_id,
                    code_hash=_hash(code, user.id),
                    expires_at=now + timedelta(seconds=settings.LOGIN_CODE_TTL_SECONDS))
    db.add(row)
    try:
        email_delivery.send(to=user.email, subject=f"{settings.APP_NAME} sign-in code",
                            body=f"Your sign-in code is {code}. It expires in "
                                 f"{settings.LOGIN_CODE_TTL_SECONDS // 60} minutes.")
    except email_delivery.DeliveryFailed:
        db.rollback()
        return Outcome("delivery_unavailable")
    db.commit()
    return Outcome("sent", challenge=str(row.id))


def verify_code(db: Session, *, email: str, challenge: str, code: str) -> Outcome:
    user = _user(db, email)
    if user is None:
        return Outcome("invalid")
    try:
        code_id = uuid.UUID(challenge)
    except (ValueError, TypeError, AttributeError):
        return Outcome("invalid")
    now = _now()
    row = db.execute(select(LoginCode).where(
        LoginCode.id == code_id, LoginCode.user_id == user.id, LoginCode.consumed_at.is_(None),
        LoginCode.expires_at > now,
    ).with_for_update()).scalar_one_or_none()
    if row is None:
        return Outcome("invalid")   # unknown, used, cancelled or expired challenge: a guess changes nothing
    if code.isdigit() and len(code) == CODE_DIGITS and hmac.compare_digest(row.code_hash, _hash(code, user.id)):
        db.execute(update(LoginCode).where(LoginCode.user_id == user.id, LoginCode.consumed_at.is_(None))
                   .values(consumed_at=now))      # this code, and the user's other live codes with it
        record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="auth.login_code",
                         resource_type="user", resource_id=user.id)
        db.commit()
        return Outcome("ok", user=user)
    row.failed_attempts += 1
    if row.failed_attempts >= settings.LOGIN_CODE_MAX_FAILURES:
        row.consumed_at = now                     # too many wrong guesses cancel this code, not the account
    db.commit()
    return Outcome("invalid")
