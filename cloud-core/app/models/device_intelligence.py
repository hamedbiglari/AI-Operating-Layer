"""
Device Intelligence: installation-continuity evidence for the official clients (ADR-138).

WHAT THIS IS
    An application installation proves, by signing a single-use server challenge with a private key it
    generated and never exports, that it is the same installation that registered earlier. That is all
    a `device_credentials` row means: *this installation, continuously*. It is not a physical machine,
    not an operating-system install, and never a person. One account may hold many credentials; one
    credential may be used by several accounts (a shared family computer, account switching).

WHAT THIS IS NOT
    * Not a fingerprint. Nothing here combines browser or hardware properties into an identifier. No
      hardware serials, MachineGuid, IMEI, UDID, MAC address or TPM material is collected.
    * Not an enforcement engine. Assessments are evidence categories with reason codes and an algorithm
      version, read by an administrator; no route consumes them to allow or deny anything.
    * Not cross-tenant. Every row carries `organization_id`; the same key registered in two tenants is two
      rows that no tenant-scoped reader can join. Platform-wide correlation needs a platform-admin
      authorization model that does not exist yet (ADR-138 "not done").

PRIVACY
    The public key is not secret; only its SHA-256 thumbprint is indexed. Network observations store a keyed,
    versioned HMAC of the client IP and of its network prefix (/24 for IPv4, /48 for IPv6) — never the raw
    address — so "these two accounts were seen on the same network" can be answered without keeping where
    that network is. Observations expire after DEVICE_OBSERVATION_RETENTION_DAYS.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Where an observation came from. Two different provenances are never compared as if equal.
PROVENANCES = ("WEB_BROWSER", "WINDOWS_CLIENT", "MACOS_CLIENT", "ANDROID_CLIENT", "IOS_CLIENT",
               "SERVER_OBSERVATION")
# What the client says protects its private key. Client-reported, so it is shown as a claim, never trusted.
KEY_STORAGE = ("hardware", "os_keystore", "browser_non_extractable", "software", "unknown")
CREDENTIAL_STATUSES = ("active", "revoked")
REVOKED_REASONS = ("user_revoked", "admin_revoked", "last_account_unlinked", "key_rotated")
CHALLENGE_PURPOSES = ("register", "verify")
OBSERVATION_KINDS = ("registered", "linked", "verified", "verification_failed", "revoked", "unlinked")
ALGORITHMS = ("ES256",)


def _q(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class DeviceCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "device_credentials"
    __table_args__ = (
        UniqueConstraint("organization_id", "key_thumbprint", name="uq_device_credentials_org_thumbprint"),
        CheckConstraint(f"provenance IN ({_q(PROVENANCES)})", name="provenance"),
        CheckConstraint(f"key_storage IN ({_q(KEY_STORAGE)})", name="key_storage"),
        CheckConstraint(f"status IN ({_q(CREDENTIAL_STATUSES)})", name="status"),
        CheckConstraint(f"algorithm IN ({_q(ALGORITHMS)})", name="algorithm"),
        # A revoked credential always says why; an active one never carries a reason. NULL-safe for the
        # same reason auth_sessions.revoked_rows_say_why is.
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_reason IS NULL) OR "
            f"(status = 'revoked' AND revoked_at IS NOT NULL AND revoked_reason IS NOT NULL "
            f"AND revoked_reason IN ({_q(REVOKED_REASONS)}))",
            name="revoked_credentials_say_why"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    # The account that proved possession first. Other accounts are in device_credential_links.
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    provenance: Mapped[str] = mapped_column(String(30), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(10), nullable=False, default="ES256")
    # base64 DER SubjectPublicKeyInfo. Public by definition; kept to verify signatures.
    public_key_spki: Mapped[str] = mapped_column(Text, nullable=False)
    # hex SHA-256 of the DER SPKI.
    key_thumbprint: Mapped[str] = mapped_column(String(64), nullable=False)
    key_storage: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    app_version: Mapped[str | None] = mapped_column(String(40))
    os_family: Mapped[str | None] = mapped_column(String(40))
    os_version: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    first_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(30))


class DeviceCredentialLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An account that has proved possession of a credential. One row per (credential, user)."""
    __tablename__ = "device_credential_links"
    __table_args__ = (
        UniqueConstraint("credential_id", "user_id", name="uq_device_credential_links_credential_user"),
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                             ondelete="CASCADE", name="fk_device_credential_links_user_org"),
        Index("ix_device_credential_links_user", "organization_id", "user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_credentials.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    first_linked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    unlinked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class DeviceChallenge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single-use nonce bound to (organization, user, purpose[, credential]). Only its hash is stored."""
    __tablename__ = "device_challenges"
    __table_args__ = (
        CheckConstraint(f"purpose IN ({_q(CHALLENGE_PURPOSES)})", name="purpose"),
        CheckConstraint("purpose = 'register' OR credential_id IS NOT NULL", name="verify_names_a_credential"),
        Index("ix_device_challenges_expires_at", "expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_credentials.id", ondelete="CASCADE"))
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class DeviceObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One thing that happened to a credential, with where it came from. Append-only; expires."""
    __tablename__ = "device_observations"
    __table_args__ = (
        CheckConstraint(f"provenance IN ({_q(PROVENANCES)})", name="provenance"),
        CheckConstraint(f"kind IN ({_q(OBSERVATION_KINDS)})", name="kind"),
        Index("ix_device_observations_credential", "credential_id", "created_at"),
        Index("ix_device_observations_network", "organization_id", "network_prefix_pseudonym"),
        Index("ix_device_observations_created_at", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_credentials.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    provenance: Mapped[str] = mapped_column(String(30), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # Machine-readable why, for failures and revocations (e.g. "bad_signature", "challenge_expired").
    reason_code: Mapped[str | None] = mapped_column(String(40))
    # Keyed HMAC pseudonyms; NULL when no address was available (NULL is not "no network").
    network_pseudonym: Mapped[str | None] = mapped_column(String(64))
    network_prefix_pseudonym: Mapped[str | None] = mapped_column(String(64))
    pseudonym_key_version: Mapped[int | None] = mapped_column(Integer)
    app_version: Mapped[str | None] = mapped_column(String(40))
