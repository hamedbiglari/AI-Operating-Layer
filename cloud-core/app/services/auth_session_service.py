"""Browser sessions — rotation, reuse detection and revocation (see app/models/auth_session.py)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth_session import AuthSession
from app.models.enums import OrganizationStatus, UserStatus
from app.models.organization import Organization
from app.models.user import User
from app.services.audit import record_audit_log

# The cookie is "<session id>.<secret>". A dot cannot appear in either half, so one split is exact.
_SEPARATOR = "."

# How long the secret replaced by the most recent rotation stays acceptable. Two tabs of the same
# site refresh together and both send the cookie the browser had; that is ordinary, and logging the
# person out for it would be a bug, not security. Long enough for a concurrent call and a network
# retry, short enough that a replayed cookie is still caught.
_ROTATION_GRACE = timedelta(seconds=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(secret: str, session_id: uuid.UUID) -> str:
    """Keyed, and bound to the session it belongs to, so a secret lifted from one row cannot be
    replayed against another."""
    return hmac.new(settings.SECRET_KEY.encode(), f"{session_id}:{secret}".encode(), hashlib.sha256).hexdigest()


@dataclass
class Outcome:
    kind: str                       # ok | invalid | expired | revoked | reuse_detected | user_inactive
    cookie: str | None = None
    user: User | None = None
    session: AuthSession | None = None


def _split(cookie: str) -> tuple[uuid.UUID, str] | None:
    raw = (cookie or "").strip()
    if raw.count(_SEPARATOR) != 1:
        return None
    head, secret = raw.split(_SEPARATOR)
    if not secret:
        return None
    try:
        return uuid.UUID(head), secret
    except ValueError:
        return None


def _issue(session: AuthSession, *, now: datetime | None = None) -> str:
    """Mint a new secret for this session and store only its hash. Returns the cookie value, which is
    the one and only moment the secret exists outside the browser. The secret being replaced is kept,
    briefly, so a second tab mid-refresh is not mistaken for an attacker."""
    if now is not None and session.token_hash:
        session.previous_token_hash = session.token_hash
        session.previous_until = now + _ROTATION_GRACE
    secret = secrets.token_urlsafe(32)
    session.token_hash = _hash(secret, session.id)
    return f"{session.id}{_SEPARATOR}{secret}"


def _trim(value: str | None, limit: int) -> str | None:
    value = (value or "").strip()
    return value[:limit] or None


def start(db: Session, *, user: User, user_agent: str | None = None, ip: str | None = None) -> Outcome:
    """Open a browser session for a user who has just proved who they are."""
    now = _now()
    session = AuthSession(
        id=uuid.uuid4(),
        organization_id=user.organization_id,
        user_id=user.id,
        token_hash="",  # replaced by _issue below, which needs the id
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        last_used_at=now,
        user_agent=_trim(user_agent, 200),
        ip=_trim(ip, 64),
    )
    cookie = _issue(session)
    db.add(session)
    record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="auth.session_started",
                     resource_type="auth_session", resource_id=session.id)
    db.commit()
    return Outcome("ok", cookie=cookie, user=user, session=session)


def _revoke(db: Session, session: AuthSession, reason: str, *, now: datetime) -> None:
    session.revoked_at = now
    session.revoked_reason = reason


def rotate(db: Session, *, cookie: str | None, user_agent: str | None = None, ip: str | None = None) -> Outcome:
    """Exchange a session cookie for the next one. Every outcome other than `ok` means the caller must
    sign in again — the wording differs, the consequence does not."""
    parsed = _split(cookie or "")
    if parsed is None:
        return Outcome("invalid")
    session_id, secret = parsed
    now = _now()
    session = db.execute(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if session is None:
        return Outcome("invalid")

    presented = _hash(secret, session.id)
    if session.revoked_at is not None:
        return Outcome("revoked")
    if session.expires_at <= now:
        _revoke(db, session, "expired", now=now)
        db.commit()
        return Outcome("expired")
    current = hmac.compare_digest(session.token_hash, presented)
    # The secret the last rotation replaced, still inside its few-second window: a second tab, not
    # a second party. It is rotated normally — both tabs share one cookie jar, so the newest cookie
    # is the one that survives either way.
    concurrent = (not current
                  and session.previous_token_hash is not None
                  and session.previous_until is not None
                  and session.previous_until > now
                  and hmac.compare_digest(session.previous_token_hash, presented))
    if not current and not concurrent:
        # A secret this session rotated away longer ago than that. Either the browser replayed an old
        # cookie or someone else holds a copy; there is no way to tell them apart, so the session ends.
        _revoke(db, session, "reuse_detected", now=now)
        record_audit_log(db, organization_id=session.organization_id, user_id=session.user_id,
                         action="auth.session_reuse_detected", resource_type="auth_session",
                         resource_id=session.id)
        db.commit()
        return Outcome("reuse_detected")

    # The session proves the cookie is current; it does not prove the account still is.
    user = db.get(User, session.user_id)
    organization = db.get(Organization, session.organization_id) if user is not None else None
    if (user is None or user.status != UserStatus.ACTIVE or organization is None
            or organization.status not in (OrganizationStatus.ACTIVE, OrganizationStatus.PENDING)):
        _revoke(db, session, "logout", now=now)
        db.commit()
        return Outcome("user_inactive")

    cookie_value = _issue(session, now=now)
    session.rotations += 1
    session.last_used_at = now
    session.user_agent = _trim(user_agent, 200) or session.user_agent
    session.ip = _trim(ip, 64) or session.ip
    db.commit()
    return Outcome("ok", cookie=cookie_value, user=user, session=session)


def end(db: Session, *, cookie: str | None) -> None:
    """Sign out. Idempotent, and deliberately silent: an unknown or already-revoked cookie is not a
    failure the caller can act on, and saying which it was would confirm a guess."""
    parsed = _split(cookie or "")
    if parsed is None:
        return
    session_id, secret = parsed
    session = db.execute(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        return
    now = _now()
    presented = _hash(secret, session.id)
    # The grace window applies here too: a tab holding the just-replaced cookie is still this user,
    # and "sign out" from it must actually sign them out.
    accepted = (hmac.compare_digest(session.token_hash, presented)
                or (session.previous_token_hash is not None
                    and session.previous_until is not None
                    and session.previous_until > now
                    and hmac.compare_digest(session.previous_token_hash, presented)))
    if not accepted:
        # Signing out is not a reason to believe the caller; a wrong secret revokes nothing.
        return
    _revoke(db, session, "logout", now=now)
    record_audit_log(db, organization_id=session.organization_id, user_id=session.user_id,
                     action="auth.session_ended", resource_type="auth_session", resource_id=session.id)
    db.commit()
