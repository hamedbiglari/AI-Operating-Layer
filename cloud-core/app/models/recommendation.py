"""
Recommendation (master spec section 33) — one product's evaluation for
one request, persisted so the decision can be audited and explained
later.

Section 33's warning is the reason this model has the shape it does:

    The internal recommendation score is NOT Google ranking, ChatGPT
    ranking, or AI ranking. It is only an internal decision signal.

So every score here is named for what it drives (a decision) and never
exposed as a rating of the product itself. Three design consequences:

1. **Every score travels with a state.** `evidence_score` alone cannot
   distinguish "no evidence exists yet" from "evidence exists and
   contradicts this" — both would be a low number. `evidence_state`
   (SignalState) carries that distinction explicitly. UNKNOWN is not
   NEGATIVE. See SignalState's docstring; this is the phase's most
   important semantic.

2. **`reason` is structured JSONB, not free text.** A future AI agent
   consuming a recommendation has to be able to answer "why this
   product, and what would change the answer" without parsing prose.
   Shape is defined by app/schemas/recommendation.py::RecommendationReason.

3. **`policy_version` is stored on every row.** Scoring WILL change.
   Without recording which policy produced a decision, historical
   recommendations become unexplainable the moment weights are
   retuned - the reproducibility requirement in the Phase 8 brief.
   This is one field beyond section 33's literal list, added for that
   reason alone (see docs/DECISIONS.md ADR-029).

`offer_id` is likewise beyond the literal list: section 33 lists
`product_id` but a recommendation is only actionable against a specific
purchasable Offer (§27 keeps price/availability there, not on Product),
and recording WHICH offer was evaluated is required to explain an
availability decision afterwards.
"""

import uuid

from sqlalchemy import CheckConstraint, Enum as SAEnum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RecommendationStatus, ResponseMode, SignalState

_SCORE_COLUMNS = (
    "relevance_score",
    "evidence_score",
    "trust_score",
    "availability_score",
    "final_score",
)


def _score_range_constraints() -> tuple:
    return tuple(
        CheckConstraint(f"{col} >= 0 AND {col} <= 1", name=f"ck_recommendations_{col}_range")
        for col in _SCORE_COLUMNS
    )


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = _score_range_constraints()

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable: a recommendation can be produced for an ad-hoc request
    # with no persisted context. SET NULL so that erasing a customer's
    # context (a legitimate privacy action) does not destroy the
    # merchant's own decision audit trail.
    customer_context_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customer_contexts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    query_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_objects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    response_mode: Mapped[ResponseMode] = mapped_column(
        SAEnum(ResponseMode, name="response_mode", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )

    relevance_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    evidence_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    trust_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    availability_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    final_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, index=True)

    # The states that make the scores interpretable - see class
    # docstring point 1. Without these, a 0.0 is ambiguous.
    evidence_state: Mapped[SignalState] = mapped_column(
        SAEnum(SignalState, name="signal_state", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SignalState.UNKNOWN,
        server_default=SignalState.UNKNOWN.value,
    )
    trust_state: Mapped[SignalState] = mapped_column(
        SAEnum(SignalState, name="signal_state", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SignalState.UNKNOWN,
        server_default=SignalState.UNKNOWN.value,
    )

    reason: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[RecommendationStatus] = mapped_column(
        SAEnum(RecommendationStatus, name="recommendation_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)

    product: Mapped["Product"] = relationship()  # noqa: F821
    customer_context: Mapped["CustomerContext | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Recommendation product_id={self.product_id} status={self.status.value} "
            f"final={self.final_score}>"
        )
