"""
CustomerContext (master spec section 32) — the minimum a recommendation
needs to know about who is asking, and nothing more.

Section 32 is emphatic about what must NOT be here: "Do not store raw
external AI conversations by default." So there is no transcript
column, no message history, no conversation id. `source` records the
CHANNEL a context arrived through (web, site search, an AI assistant
integration, the API) — never what was said. `topic` is one short
string, not a dialogue.

Every identity field is nullable on purpose. A genuinely anonymous
context (`context_type=ANONYMOUS`, no `customer_id`, no `session_id`)
is fully usable for a single recommendation call — the engine never
requires an identity to function, which is what makes "privacy-safe by
default" a property of the schema rather than a promise in a docstring.

`consent_status` is enforced by a HARD GATE in
app/services/recommendation_policy.py, not by a score penalty: a
WITHDRAWN context produces no recommendations at all, and no amount of
relevance can outweigh that.

The Phase 8 brief warns against building a CRM here. This is not one:
there is no contact info, no address, no order history, no long-term
profile. `preferences` is a small JSONB bag for legitimately-provided
preferences (e.g. "prefers organic"), not a behavioural dossier.
"""

import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ConsentStatus,
    ContextSource,
    ContextType,
    IntentType,
    NeedLevel,
    PriceSensitivity,
    PurchaseIntent,
)


class CustomerContext(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_contexts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Opaque merchant-side identifiers. Deliberately plain strings with
    # no FK: this system does not own the merchant's customer table and
    # must not require one to exist.
    customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    context_type: Mapped[ContextType] = mapped_column(
        SAEnum(ContextType, name="context_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ContextType.ANONYMOUS,
        server_default=ContextType.ANONYMOUS.value,
    )
    # Reuses Phase 6's IntentType rather than inventing a parallel
    # vocabulary - the intent behind a context and the intent behind a
    # query are the same kind of fact, and two enums would drift.
    intent: Mapped[IntentType | None] = mapped_column(
        SAEnum(IntentType, name="intent_type", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    topic: Mapped[str | None] = mapped_column(String(500), nullable=True)

    purchase_intent: Mapped[PurchaseIntent] = mapped_column(
        SAEnum(PurchaseIntent, name="purchase_intent", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PurchaseIntent.NONE,
        server_default=PurchaseIntent.NONE.value,
    )
    evidence_need: Mapped[NeedLevel] = mapped_column(
        SAEnum(NeedLevel, name="need_level", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=NeedLevel.NORMAL,
        server_default=NeedLevel.NORMAL.value,
    )
    trust_need: Mapped[NeedLevel] = mapped_column(
        SAEnum(NeedLevel, name="need_level", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=NeedLevel.NORMAL,
        server_default=NeedLevel.NORMAL.value,
    )
    price_sensitivity: Mapped[PriceSensitivity] = mapped_column(
        SAEnum(PriceSensitivity, name="price_sensitivity", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PriceSensitivity.UNKNOWN,
        server_default=PriceSensitivity.UNKNOWN.value,
    )
    # A category/brand/product the person expressed interest in, as
    # free text - a hint for candidate generation, never a hard filter.
    product_interest: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    consent_status: Mapped[ConsentStatus] = mapped_column(
        SAEnum(ConsentStatus, name="consent_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ConsentStatus.NOT_REQUIRED,
        server_default=ConsentStatus.NOT_REQUIRED.value,
        index=True,
    )
    source: Mapped[ContextSource] = mapped_column(
        SAEnum(ContextSource, name="context_source", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ContextSource.API,
        server_default=ContextSource.API.value,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CustomerContext id={self.id} type={self.context_type.value} consent={self.consent_status.value}>"
