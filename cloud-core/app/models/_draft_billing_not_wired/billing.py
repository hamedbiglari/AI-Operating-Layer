"""
Billing / entitlement / AI-wallet domain models — DRAFT (Phase 13
follow-up, ADR-082 through ADR-086).

STATUS: DESIGNED, NOT MIGRATED, NOT RUN. This module was written against
the project's existing conventions (UUIDPrimaryKeyMixin, TimestampMixin,
composite tenant foreign keys, the `_enum()` helper) so that a real
implementation session — one with an actual Postgres instance, Alembic,
and the rest of the dependency set — can start from something concrete
instead of a blank file. It has been syntax-checked (`python -m
py_compile`) and reviewed for consistency with `PageView` and
`Organization` in this same package. It has NOT been imported against a
live SQLAlchemy metadata registry, has NOT had a migration generated from
it, and has NOT been exercised by a single test. Do not treat this file
as "implemented" in the sense the project's own status taxonomy uses —
it is DESIGNED only, per the taxonomy in `docs/DECISIONS.md` ADR-001.

WHY THREE SEPARATE LEDGERS, NOT ONE "BALANCE"

Subscription, Wallet and Entitlement answer three different questions
(see ADR-082) and are modelled as three independent aggregates rather
than fields on one table:

    Subscription  -> "what plan is this organization on, and until when?"
    Wallet         -> "how much AI processing budget is available?"
    Entitlement    -> "can this organization do THIS specific thing,
                       right now?" — derived, not stored as a single flag

Entitlement is deliberately NOT a persisted yes/no per capability. It is
*resolved* at request time from (a) the organization's current
Subscription state, (b) any ACTIVE TrialClaim, and (c) the capability
matrix in ENTITLEMENT_MATRIX.md — the matrix is data (versioned,
admin-editable), not a chain of if-statements, so extending the matrix
never requires touching this module or its call sites.

WHY A LEDGER, NOT A MUTABLE BALANCE COLUMN

`Wallet.available_cents` / `reserved_cents` / `consumed_cents` are
DERIVED, CACHED integers — never the authoritative record. The
authoritative record is `LedgerEntry`, append-only, one row per financial
event (ADR-084). A cached balance can always be reconstructed by summing
`LedgerEntry.amount_cents` for the wallet; if it cannot, the cache is
wrong and the ledger — not the cache — is trusted. This is the same
"recompute, never increment" discipline ADR-080 already established for
`content_view_daily`.

MONEY / TOKENS

All money is integer minor units (cents) with an explicit `currency`
column — never float (§218 of the owner's billing prompt; this project's
own money-handling precedent is worth stating even though no prior phase
had a money column). Token counts are plain integers. Estimated cost and
actual provider cost are separate columns wherever both can exist,
because they are different claims (ADR-086) — this file does not blur
them.

TENANT ISOLATION

Every organization-scoped table repeats the `PageView` pattern: a plain
`organization_id` column PLUS, where the row also references another
tenant-scoped entity (e.g. a `LedgerEntry` referencing a `Wallet`), a
composite `ForeignKeyConstraint` that pins both columns together so a
row can never point at another organization's parent by mistake — this
is what actually prevents the cross-tenant billing leaks in the owner's
prompt (§108, §183, §234), not an application-layer check alone.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _enum(cls, name):
    return SAEnum(cls, name=name, values_callable=lambda e: [m.value for m in e])


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------

import enum


class PlanTier(str, enum.Enum):
    """The catalog is data (see `Plan`/`PlanVersion`), so this enum is
    deliberately small and structural, not a place to hardcode pricing or
    feature lists (owner's prompt §51: "Do not hardcode plan names into
    business logic"). It exists only so Subscription/Entitlement code can
    ask "is this at least Pro-tier" without string comparison."""

    BASIC = "basic"
    PRO = "pro"


class SubscriptionStatus(str, enum.Enum):
    """Only the states this system actually needs (owner's prompt §64:
    "Do not invent unsupported payment states")."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    GRACE_PERIOD = "grace_period"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REVOKED = "revoked"


class TrialClaimStatus(str, enum.Enum):
    ELIGIBLE = "eligible"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CONVERTED = "converted"


class LedgerEntryType(str, enum.Enum):
    """One row per financial event (ADR-084). Adding a new kind of
    financial event means adding a value here, never a new mutable
    balance field somewhere else."""

    PAYMENT_CAPTURED = "payment_captured"
    REFUND = "refund"
    CREDIT_GRANTED = "credit_granted"
    CREDIT_REVERSED = "credit_reversed"
    WALLET_PURCHASE = "wallet_purchase"
    AI_USAGE_CHARGE = "ai_usage_charge"
    PLATFORM_FEE = "platform_fee"
    MANUAL_ADJUSTMENT = "manual_adjustment"
    RESERVATION = "reservation"
    RELEASE = "release"


class WalletReservationStatus(str, enum.Enum):
    """The three-step reserve -> settle -> release cycle from ADR-086.
    A reservation is never deleted on settlement — it is marked SETTLED so
    the ledger stays reconstructable (§217 idempotency, §235 concurrency)."""

    HELD = "held"
    SETTLED = "settled"
    RELEASED = "released"
    EXPIRED = "expired"


# --------------------------------------------------------------------------
# Catalog (global, not tenant-scoped)
# --------------------------------------------------------------------------


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The plan catalog. `Plan` is the stable identity (slug, tier);
    `PlanVersion` (documented, not yet drafted as a class — see
    BILLING_DATA_MODEL.md) carries the actual price/entitlements with an
    effective-date range, so a past invoice stays explainable against the
    plan version that was active when the payment happened (owner's
    prompt §102: "Never overwrite historical pricing semantics"). This
    class intentionally carries NO price column."""

    __tablename__ = "billing_plans"

    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tier: Mapped[PlanTier] = mapped_column(_enum(PlanTier, "billing_plan_tier"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_purchasable: Mapped[bool] = mapped_column(nullable=False, default=True)


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per organization's current subscription lifecycle. History
    (previous plans, past renewals/cancellations — owner's prompt §214)
    is NOT stored by mutating this row; it lives in `LedgerEntry`-adjacent
    `SubscriptionEvent` records (documented, not drafted here) so this
    table only ever holds current state, the same "current state table +
    append-only history table" split used for `Subscription` vs
    `LedgerEntry` throughout this module."""

    __tablename__ = "billing_subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_billing_subscriptions_organization"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_plans.id"), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        _enum(SubscriptionStatus, "billing_subscription_status"), nullable=False
    )
    current_period_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(nullable=False, default=False)
    # NULL means "not yet resolved" per this module's NULL-vs-zero rule —
    # never assume ACTIVE just because canceled_at is unset.
    canceled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class TrialClaim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A first-class, server-enforced 7-day Pro trial record (owner's
    prompt §54–56, ADR-085). The uniqueness constraint is the entire
    anti-abuse mechanism for "cannot be claimed repeatedly by
    logout/relogin" — it is a database constraint, not a frontend check,
    per this project's standing rule that the client is never trusted to
    declare its own entitlement."""

    __tablename__ = "billing_trial_claims"
    __table_args__ = (
        # One trial per organization, ever, by default (owner's prompt
        # §54: "cannot be stacked... cannot be endlessly reset").
        UniqueConstraint("organization_id", name="uq_billing_trial_claims_organization"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[TrialClaimStatus] = mapped_column(
        _enum(TrialClaimStatus, "billing_trial_claim_status"), nullable=False,
        default=TrialClaimStatus.ELIGIBLE,
    )
    start_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    claimed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


# --------------------------------------------------------------------------
# Wallet / ledger (tenant-scoped)
# --------------------------------------------------------------------------


class Wallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The AI processing budget, independent of Subscription (ADR-082:
    "Subscription answers what features; Wallet answers what budget").
    `available_cents` / `reserved_cents` / `consumed_cents` are a cache —
    see the module docstring. Currency is explicit per owner's prompt
    §221; this draft assumes single-currency wallets, documented as a
    scoping decision for the real implementation to confirm or revisit."""

    __tablename__ = "billing_wallets"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_billing_wallets_organization"),
        CheckConstraint("available_cents >= 0", name="ck_billing_wallets_available_non_negative"),
        CheckConstraint("reserved_cents >= 0", name="ck_billing_wallets_reserved_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    available_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The timestamp this cache was last reconciled against LedgerEntry —
    # rendered in the UI per §127 ("Dashboard Data Freshness"), never
    # presented as if the cache were itself the source of truth.
    balance_recomputed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class LedgerEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only. Never UPDATEd, never DELETEd (ADR-084). A correction
    is a new compensating row (`MANUAL_ADJUSTMENT` or `REFUND`), never an
    edit to a past row — the same rule the owner's prompt states at
    §190/§104 ("Corrections must be compensating ledger entries") and the
    exact mechanism ADR-080 already uses for `content_view_daily`
    ("recompute, never increment") applied to money instead of counts."""

    __tablename__ = "billing_ledger_entries"
    __table_args__ = (
        # event_key is minted by whatever caused the entry (a payment
        # webhook's event id, a job settlement's job id + attempt) so a
        # retried webhook or a redelivered settlement cannot double-post —
        # the same idempotency mechanism as PageView.event_key.
        UniqueConstraint(
            "organization_id", "event_key", name="uq_billing_ledger_entries_organization_event_key"
        ),
        ForeignKeyConstraint(
            ["wallet_id", "organization_id"],
            ["billing_wallets.id", "billing_wallets.organization_id"],
            name="fk_billing_ledger_entries_wallet_organization",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        _enum(LedgerEntryType, "billing_ledger_entry_type"), nullable=False
    )
    # Signed: positive credits the wallet, negative debits it. A single
    # signed column, not separate credit/debit columns, so "sum this
    # wallet's entries" is always just SUM(amount_cents).
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Free-form provenance pointer (payment id, job id, admin actor id) —
    # deliberately JSONB rather than N nullable FK columns, because which
    # entry types reference which entities varies and this table must
    # stay append-only-safe (adding a new FK later would be a migration
    # touching every historical row's NULL-ness, which this avoids).
    reference: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


# --------------------------------------------------------------------------
# NOT drafted as classes in this file — documented at schema level only in
# BILLING_DATA_MODEL.md, to keep this first pass reviewable in one sitting:
# PlanVersion, Payment, PaymentEvent, Invoice, WalletReservation,
# UsageRecord, AICostRecord, ProviderPricingVersion, SubscriptionEvent.
# Each needs the same tenant-FK and append-only treatment as above; none
# of them introduce a new pattern this file hasn't already established.
