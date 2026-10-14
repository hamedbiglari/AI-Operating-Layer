"""
Installation & InstallationCredential — the generic MACHINE IDENTITY
model (ADR-036).

This is deliberately NOT a WordPress model. Master spec section 38 says
the plugin "should handle authentication" without specifying a
mechanism, and building a WordPress-shaped credential table would mean
building a second one for MCP and a third for the next CMS. So the
model names what is actually common to every machine client:

    credential  ->  installation  ->  organization

**Tenant identity is derived, never supplied.** There is no code path
where an adapter sends an `organization_id` and is believed. The
credential resolves to exactly one Installation, which belongs to
exactly one Organization, and that is the only tenant the request can
ever act in. This is the difference between authentication and
authorization being separate concerns and them being the same field in
a JSON body.

**Secrets are never stored.** `InstallationCredential` holds a bcrypt
hash of the secret and a non-secret `key_id` used for lookup. The
plaintext secret is returned exactly once, at creation, and cannot be
recovered afterwards - the same discipline `User.password_hash`
already follows (reusing `app/security/passwords.py`, not a second
hashing scheme).

**Rotation preserves history.** Rotating issues a new credential and
marks the old one ROTATED rather than deleting it, so an audit entry
that references a retired key still resolves. Revocation is terminal.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Enum as SAEnum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AdapterScope, AdapterType, CredentialStatus, InstallationStatus


class Installation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "installations"
    __table_args__ = (
        # A parent-side composite unique so children can carry a
        # composite FK back to (id, organization_id) - see ADR-037.
        UniqueConstraint("id", "organization_id", name="uq_installations_id_organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional: an installation may be scoped to one site, or act for
    # the whole organization. SET NULL, not CASCADE - removing a site
    # must not silently destroy the integration's audit history.
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter_type: Mapped[AdapterType] = mapped_column(
        SAEnum(AdapterType, name="adapter_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    status: Mapped[InstallationStatus] = mapped_column(
        SAEnum(InstallationStatus, name="installation_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=InstallationStatus.ACTIVE,
        server_default=InstallationStatus.ACTIVE.value,
        index=True,
    )
    # Where this installation lives, for operator diagnosis. Never used
    # for authorization - a self-reported URL is not an identity.
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    credentials: Mapped[list["InstallationCredential"]] = relationship(  # noqa: F821
        back_populates="installation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Installation id={self.id} type={self.adapter_type.value} status={self.status.value}>"


class InstallationCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "installation_credentials"
    __table_args__ = (
        UniqueConstraint("key_id", name="uq_installation_credentials_key_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Public, non-secret lookup handle. Indexed and unique because it
    # is what an incoming request is resolved by - the secret itself is
    # never queried, only compared against the stored hash.
    key_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Capability grants. ARRAY of plain strings rather than a join
    # table: scopes are a short, closed, read-mostly list checked on
    # every request, and a join table would add a query to the hot
    # auth path for no expressive gain.
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, server_default="{}"
    )

    status: Mapped[CredentialStatus] = mapped_column(
        SAEnum(CredentialStatus, name="credential_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=CredentialStatus.ACTIVE,
        server_default=CredentialStatus.ACTIVE.value,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Which credential this one replaced, for rotation audit.
    rotated_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("installation_credentials.id", ondelete="SET NULL"),
        nullable=True,
    )

    installation: Mapped["Installation"] = relationship(back_populates="credentials")

    @property
    def granted_scopes(self) -> set[AdapterScope]:
        """Unknown scope strings are ignored rather than raising - a
        credential issued before a scope was renamed must still
        authenticate, just without the unrecognised capability."""
        out: set[AdapterScope] = set()
        for raw in self.scopes or []:
            try:
                out.add(AdapterScope(raw))
            except ValueError:
                continue
        return out

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InstallationCredential key_id={self.key_id} status={self.status.value}>"
