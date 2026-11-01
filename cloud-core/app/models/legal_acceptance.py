"""
Legal acceptance (ADR-139): the user ticked "I accept the Terms of Use and the Privacy Policy" at sign-in.

One row per (user, terms version). `consents` lists what that tick covered — the clients show all of it next to
the checkbox — so no separate prompt is shown later for any of them (e.g. installation verification, ADR-138).
The version is operator configuration (CLIENT_TERMS_VERSION); publishing a new version means the next sign-in
asks again. Rows are evidence of what was shown and accepted, kept with the account and deleted with it.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LegalAcceptance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "legal_acceptances"
    __table_args__ = (
        UniqueConstraint("user_id", "terms_version", name="uq_legal_acceptances_user_version"),
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                             ondelete="CASCADE", name="fk_legal_acceptances_user_org"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    terms_version: Mapped[str] = mapped_column(String(40), nullable=False)
    # What the one tick covered, e.g. ["terms", "privacy", "device_intelligence"].
    consents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Where it was given: "windows" | "macos" | "android" | "ios" | "web". Client-reported, for the record only.
    client_platform: Mapped[str | None] = mapped_column(String(20))
