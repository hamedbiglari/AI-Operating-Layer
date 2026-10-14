"""
AI access policy (Phase 13, ADR-077).

THE MERCHANT'S DECISION, STORED ONCE

One row = one decision: *for this agent (or this class of agent), fetching
for this purpose, the answer is free / paid / forbidden.* This is the table
behind "block the training crawlers, keep answering open".

PRECEDENCE — THE ONLY THING THAT MAKES THIS PREDICTABLE

Four levels, most specific first:

    1. agent_id + purpose          "GPTBot, for training"
    2. agent_id, purpose NULL      "GPTBot, anything"
    3. actor_type + purpose        "any AI crawler, for training"
    4. actor_type, purpose NULL    "any AI crawler, anything"

First match wins and evaluation stops. No scoring, no combining, no
"strictest wins" — a merchant must be able to read the table and predict
the outcome, and a rule engine that blends four rows cannot be read.

If nothing matches the decision is `NOT_CONFIGURED`, the request is
allowed, and the dashboard says so. Defaulting to FORBIDDEN would take the
merchant's site off the answer surfaces the moment Phase 13 ships, without
anyone choosing that. Defaulting to FREE and *calling* it a policy would
be worse: it would report a decision nobody made.

WHAT `PAID` DOES AND DOES NOT DO

`PAID` records intent and produces HTTP 402 with a `Link` to the merchant's
terms. There is no payment processing, no metering and no settlement in
Phase 13, and the model deliberately carries no price column — a number
here would look like a working price when nothing can charge it. What is
owed and how it is collected is out of scope and recorded as such.
"""

import uuid

from sqlalchemy import (
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AccessPurpose, AccessTier, ActorType


def _enum(cls, name):
    return SAEnum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class AccessPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "access_policies"
    __table_args__ = (
        # Identity of a rule. `nulls_not_distinct` matters: without it
        # Postgres would happily store two "GPTBot, any purpose" rows,
        # because NULL != NULL, and precedence level 2 would become
        # ambiguous.
        UniqueConstraint(
            "organization_id",
            "agent_id",
            "actor_type",
            "purpose",
            name="uq_access_policies_rule_identity",
            postgresql_nulls_not_distinct=True,
        ),
        # Composite FK: the agent must belong to the same tenant as the
        # policy. This is the Phase 9 ADR-037 pattern - the database
        # refuses a cross-tenant parent, not just the service layer.
        ForeignKeyConstraint(
            ["agent_id", "organization_id"],
            ["ai_agents.id", "ai_agents.organization_id"],
            name="fk_access_policies_agent_organization",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Exactly one of agent_id / actor_type carries the subject. Both NULL
    # is meaningless and is rejected by the service layer with a 422; the
    # check is not expressible as a simple CHECK constraint without
    # duplicating the precedence rules in SQL, so it is enforced in one
    # place (`access_policy_service.validate_rule`) and tested directly.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[ActorType | None] = mapped_column(
        _enum(ActorType, "actor_type"), nullable=True
    )
    # NULL = "any purpose".
    purpose: Mapped[AccessPurpose | None] = mapped_column(
        _enum(AccessPurpose, "access_purpose"), nullable=True
    )

    tier: Mapped[AccessTier] = mapped_column(
        _enum(AccessTier, "access_tier"),
        nullable=False,
        default=AccessTier.UNSET,
        server_default=AccessTier.UNSET.value,
    )

    # Materialised precedence, written by the service, never by a client.
    # Stored rather than computed at read time so the evaluation query is
    # one indexed ORDER BY instead of four round trips.
    specificity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Shown to the agent on a 402/403 and to the merchant in the audit
    # trail. Free text on purpose: the reason a merchant blocks someone is
    # not a closed vocabulary.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sent as a `Link: <...>; rel="terms-of-service"` header on 402.
    terms_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        subject = f"agent={self.agent_id}" if self.agent_id else f"type={self.actor_type}"
        return f"<AccessPolicy {subject} purpose={self.purpose} -> {self.tier.value}>"
