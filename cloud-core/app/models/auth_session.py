"""
Browser session: the long-lived half of a signed-in website visitor (ADR-129).

The website holds its access token in a JavaScript variable and nothing else. A variable dies with the
tab, so the visitor needs something durable to get a fresh access token from — and that something must
be unreadable to page scripts, or the whole arrangement buys nothing. It is this row, addressed by an
HttpOnly cookie.

WHAT IS IN THE COOKIE
    "<session id>.<secret>"
Only an HMAC of the secret is stored, keyed with SECRET_KEY, exactly as `login_codes` stores a code.
Reading this table therefore does not yield a usable cookie.

ROTATION AND REUSE (OAuth 2.1 / BCP for browser-based apps)
Every refresh issues a new secret and invalidates the old one. If a secret that has already been
rotated away is presented again, two parties hold the cookie — the legitimate browser and a thief —
and there is no way to tell which one is calling. The session is revoked outright rather than guessed
about; the user signs in again.

Two tabs of the same site refresh at the same moment and both present the same cookie, which is
ordinary behaviour and not an attack. So the secret replaced by the most recent rotation stays
acceptable for a few seconds (`previous_token_hash` until `previous_until`): within that window the
second caller is rotated normally, and outside it — or for any older secret — the session is
revoked. The window is what separates a concurrent refresh from a replay.

`expires_at` is absolute and rotation never extends it, so a stolen cookie cannot be refreshed
indefinitely: it dies with the session it was cut from.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Why a session stopped being usable. Recorded rather than inferred, because "the user signed out" and
# "someone replayed a rotated cookie" need different answers from support.
REVOKED_REASONS = ("logout", "reuse_detected", "expired")


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                             ondelete="CASCADE", name="fk_auth_sessions_user_org"),
        # The sweep for a user's live sessions, and the expiry sweep, are the only non-primary-key reads.
        Index("ix_auth_sessions_user_live", "user_id", "revoked_at"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
        # A revoked session always says why, and only in these words — the vocabulary holds in the
        # schema rather than only in the one service that writes it.
        # `revoked_reason IS NOT NULL` is not redundant: in SQL, NULL IN (...) is NULL, and a CHECK
        # whose expression is NULL passes. Without it a revoked row with no reason would be accepted.
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_reason IS NOT NULL AND revoked_reason IN "
            f"({', '.join(repr(r) for r in REVOKED_REASONS)}))",
            name="revoked_rows_say_why"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # HMAC-SHA256 of the current secret. Replaced on every rotation.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # The secret the last rotation replaced, honoured only until `previous_until`.
    previous_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rotations: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Truncated and kept only so a user can recognise their own sessions; never used for authorization,
    # because both values are attacker-controlled.
    user_agent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
