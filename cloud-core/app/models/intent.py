"""
Intent: what a Query is actually asking for (master spec section 24) —
"قیمت ترنجبین" -> PRICE, "کجا بخریم" -> TRANSACTIONAL. A Query can have
more than one Intent row (multi-intent classification); `is_primary`
marks the single dominant one, enforced by a partial unique index
(at most one primary Intent per query) so "which intent is THE intent
for this query" is always answerable unambiguously.

`entity_id` is a real, immediately-usable FK — `Entity` already exists
(Phase 2). `product_id` is a plain nullable UUID with NO FK constraint
yet, because `products` doesn't exist until Phase 7 — this mirrors an
already-shipped precedent in this exact codebase:
`relationships.source_id` was added as a plain nullable UUID in the
Phase 2 migration, then Phase 3's migration `0004` added the deferred
FK once `sources` existed (see `Relationship`'s own docstring). A
future Phase 7 migration adds `intents.product_id`'s FK the same way,
via `op.create_foreign_key`, never by editing this migration.

`classification_source`/`reason`/`is_primary` are additive beyond
section 24's literal 7 fields, needed for explainability (section 10's
"why" question, applied here to intent classification: which rule
fired, or was this a human override) and for supporting more than one
Intent per query without ambiguity about which one is authoritative.
Intent rows are immutable once created — a human override creates a
NEW row (classification_source=MANUAL) rather than editing the rule
engine's row in place, so the classification history is never lost.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, Enum as SAEnum, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import IntentClassificationSource, IntentType


class Intent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "intents"
    __table_args__ = (
        # At most one primary Intent per query - a partial unique
        # index, the same defense-in-depth discipline as Claim's XOR
        # CHECK constraint, just expressed as a partial index since
        # this is a "unique among a filtered subset" rule rather than
        # a same-row invariant.
        Index(
            "uq_intents_query_id_primary",
            "query_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    # created_at only, no TimestampMixin - immutable classification
    # record (see module docstring).
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    intent_type: Mapped[IntentType] = mapped_column(
        SAEnum(IntentType, name="intent_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # No FK yet - see module docstring. Deliberately plain UUID.
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    classification_source: Mapped[IntentClassificationSource] = mapped_column(
        SAEnum(
            IntentClassificationSource, name="intent_classification_source",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=IntentClassificationSource.RULE_ENGINE,
        server_default=IntentClassificationSource.RULE_ENGINE.value,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    query: Mapped["Query"] = relationship(back_populates="intents")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Intent query_id={self.query_id} type={self.intent_type.value} primary={self.is_primary}>"
