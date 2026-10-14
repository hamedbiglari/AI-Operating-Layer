"""
AI agent registry (Phase 13, ADR-076).

WHAT THIS IS

One row per distinct automated client this organization has actually seen,
plus the shipped seed list. It answers one question the merchant asked
directly: *which AIs are coming to my site?*

WHAT THIS IS NOT

**It is not an allow-list.** That distinction is the whole design. A
registry that only contains agents somebody approved in advance cannot
answer the question above — the interesting agent is always the one nobody
had heard of yet. So `upsert_seen()` creates a row for anything that
arrives, marks it `DISCOVERED`, and leaves its access tier `UNSET`. The
merchant then decides. Nothing is ever dropped for being unrecognised.

WHY THE SIGNATURE IS STORED, NOT THE WHOLE USER-AGENT

`signature` is the matched needle (`GPTBot`) or, for an unmatched client,
a normalised fingerprint of the User-Agent. Grouping on the raw header
would produce a new "agent" per version bump and per build id, which is
noise, not intelligence. `sample_user_agent` keeps one truncated example
so a human can still see what the raw string looked like.

CONFIDENCE IS CARRIED, NOT DISCARDED

`AIOL_Actors` was built on the rule that a User-Agent is a claim, not an
identity (ADR-046). That rule survives the move into Core: every
observation carries an `ActorConfidence`, header matches are `DETECTED`
and never `VERIFIED`, and `verification_note` states in words what was and
was not checked. A dashboard row that says "GPTBot" must be readable as
"something calling itself GPTBot".
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Enum as SAEnum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AccessPurpose,
    ActorConfidence,
    ActorType,
    AgentRegistrationOrigin,
)


def _enum(cls, name):
    return SAEnum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class AiAgent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A distinct automated client, per organization.

    Per-organization rather than global on purpose: two merchants can
    legitimately reach different conclusions about the same crawler, and a
    global row would mean one merchant's decision leaked into another's
    tenant. The seed list is copied into each organization at first use
    rather than shared.
    """

    __tablename__ = "ai_agents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "signature", name="uq_ai_agents_organization_signature"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The matched needle, or a normalised fingerprint for an unmatched client.
    signature: Mapped[str] = mapped_column(String(160), nullable=False)
    # Human-facing name. For a discovered agent this starts equal to the
    # signature; a merchant may rename it.
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    # NULL, not "Unknown Inc." - we do not invent an operator.
    vendor: Mapped[str | None] = mapped_column(String(120), nullable=True)

    actor_type: Mapped[ActorType] = mapped_column(
        _enum(ActorType, "actor_type"), nullable=False, index=True
    )
    declared_purpose: Mapped[AccessPurpose] = mapped_column(
        _enum(AccessPurpose, "access_purpose"),
        nullable=False,
        default=AccessPurpose.UNKNOWN,
        server_default=AccessPurpose.UNKNOWN.value,
    )
    confidence: Mapped[ActorConfidence] = mapped_column(
        _enum(ActorConfidence, "actor_confidence"),
        nullable=False,
        default=ActorConfidence.UNKNOWN,
        server_default=ActorConfidence.UNKNOWN.value,
    )
    origin: Mapped[AgentRegistrationOrigin] = mapped_column(
        _enum(AgentRegistrationOrigin, "agent_registration_origin"),
        nullable=False,
        default=AgentRegistrationOrigin.DISCOVERED,
        server_default=AgentRegistrationOrigin.DISCOVERED.value,
        index=True,
    )

    # States in words what was and was not checked. Rendered next to the
    # confidence badge so "Detected" is never read as "Verified".
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    sample_user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)

    first_seen_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, index=True
    )
    # BigInteger: a busy site can pass 2^31 observations for one crawler.
    observation_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AiAgent {self.signature} {self.actor_type.value} seen={self.observation_count}>"
