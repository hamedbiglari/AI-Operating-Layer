"""
Passwordless organization sign-up (ADR-106).

request -> a 6-digit code is emailed; only its HMAC is stored, with the pending organization details.
verify  -> the organization, its owner and a token are created, once.

Rules: 10-minute expiry, one-time use, at most 5 wrong attempts per request, a resend cooldown and an
hourly cap per email and per IP, no account enumeration in the response, no code in any log, and no
password anywhere in the flow.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.organization import Organization
from app.models.signup_code import SignupCode
from app.models.user import User
from app.services import email_delivery

TTL_SECONDS = 600
RESEND_SECONDS = 60
MAX_ATTEMPTS = 5
MAX_PER_EMAIL_PER_HOUR = 5
MAX_PER_IP_PER_HOUR = 20


@dataclass
class Outcome:
    kind: str                       # sent | cooldown | rate_limited | delivery_unavailable | ok | invalid | expired | used | too_many_attempts | conflict
    retry_after_seconds: int | None = None
    organization: Organization | None = None
    user: User | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(code: str, row_id) -> str:  # noqa: ANN001
    secret = settings.SECRET_KEY
    key = (secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)).encode()
    return hmac.new(key, f"{row_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _email_taken(db: Session, email: str) -> bool:
    return db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none() is not None


def request_signup(db: Session, *, email: str, organization_name: str, owner_name: str, ip: str | None) -> Outcome:
    email = email.strip().lower()
    now = _now()
    hour_ago = now - timedelta(hours=1)
    recent = db.execute(select(SignupCode).where(SignupCode.email == email, SignupCode.created_at > hour_ago)
                        .order_by(SignupCode.created_at.desc())).scalars().all()
    if recent and (now - recent[0].created_at).total_seconds() < RESEND_SECONDS:
        return Outcome("cooldown", retry_after_seconds=int(RESEND_SECONDS - (now - recent[0].created_at).total_seconds()))
    if len(recent) >= MAX_PER_EMAIL_PER_HOUR:
        return Outcome("rate_limited", retry_after_seconds=3600)
    if ip:
        per_ip = db.execute(select(func.count()).select_from(SignupCode)
                            .where(SignupCode.request_ip == ip, SignupCode.created_at > hour_ago)).scalar_one()
        if per_ip >= MAX_PER_IP_PER_HOUR:
            return Outcome("rate_limited", retry_after_seconds=3600)
    if not email_delivery.is_configured():
        return Outcome("delivery_unavailable")
    row = SignupCode(email=email, organization_name=organization_name.strip(), owner_name=owner_name.strip(),
                     code_hash="", expires_at=now + timedelta(seconds=TTL_SECONDS), request_ip=ip)
    db.add(row)
    db.flush()
    # An address that already has an account gets the same answer, but no code and no pending row.
    if _email_taken(db, email):
        db.delete(row)
        db.commit()
        return Outcome("sent", retry_after_seconds=RESEND_SECONDS)
    code = f"{secrets.randbelow(1_000_000):06d}"
    row.code_hash = _hash(code, row.id)
    db.commit()
    email_delivery.send(to=email, subject="Your AI Operating Layer sign-up code",
                        body=f"Your sign-up code is {code}. It expires in {TTL_SECONDS // 60} minutes. "
                             "If you did not request an account, ignore this email.")
    return Outcome("sent", retry_after_seconds=RESEND_SECONDS)


def verify_signup(db: Session, *, email: str, code: str) -> Outcome:
    from app.services import auth_service

    email = email.strip().lower()
    now = _now()
    row = db.execute(select(SignupCode).where(SignupCode.email == email, SignupCode.consumed_at.is_(None))
                     .order_by(SignupCode.created_at.desc()).limit(1).with_for_update()).scalar_one_or_none()
    if row is None:
        return Outcome("invalid")
    if row.expires_at <= now:
        return Outcome("expired")
    if row.attempts >= MAX_ATTEMPTS:
        return Outcome("too_many_attempts")
    if not (len(code) == 6 and code.isdigit() and hmac.compare_digest(row.code_hash, _hash(code, row.id))):
        row.attempts += 1
        db.commit()
        return Outcome("invalid")
    row.consumed_at = now                      # one-time use, before anything is created
    db.flush()
    if _email_taken(db, email):                # someone registered this address meanwhile
        db.commit()
        return Outcome("conflict")
    organization, owner = auth_service.register_organization(
        db, organization_name=row.organization_name, owner_email=email, owner_name=row.owner_name, owner_password=None)
    row.organization_id = organization.id
    db.commit()
    db.refresh(owner)
    return Outcome("ok", organization=organization, user=owner)
