"""
Wallet, append-only ledger, reservations, payments and webhook events (ADR-104; follows the
ADR-084/086 design: ledger is the truth, balances are derived; reserve -> settle -> release).

Money is integer minor units (cents) in one currency per wallet. Nothing here moves real money:
the only payment provider implemented is `sandbox` (enabled explicitly for development); a real
payment provider is BLOCKED_EXTERNAL_DEPENDENCY until credentials exist.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, BigInteger, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

LEDGER_TYPES = ("payment_captured", "refund", "credit_granted", "credit_reversed", "ai_usage_charge",
                "manual_adjustment", "reservation", "release")
RESERVATION_STATES = ("held", "settled", "released", "expired")
PAYMENT_STATES = ("pending", "succeeded", "failed", "cancelled")


def _in(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class Wallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_wallets_organization"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")


class WalletLedgerEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only: rows are never updated or deleted (database trigger)."""
    __tablename__ = "wallet_ledger_entries"
    __table_args__ = (
        CheckConstraint(f"entry_type IN ({_in(LEDGER_TYPES)})", name="entry_type"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_ledger_idempotency"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)       # signed: + credit to available, - debit
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)


class WalletReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallet_reservations"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(RESERVATION_STATES)})", name="status"),
        CheckConstraint("amount_cents > 0", name="positive_amount"),
        CheckConstraint("settled_cents IS NULL OR (settled_cents >= 0 AND settled_cents <= amount_cents)", name="settled_within_hold"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_reservation_idempotency"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    settled_cents: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="held")
    reference: Mapped[str | None] = mapped_column(String(300))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(PAYMENT_STATES)})", name="status"),
        CheckConstraint("amount_cents > 0", name="positive_amount"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_payment_idempotency"),
        UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)


class PaymentWebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Every accepted provider event, once. Replays are rejected by the unique event id."""
    __tablename__ = "payment_webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_event"),)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict | None] = mapped_column(JSON)
