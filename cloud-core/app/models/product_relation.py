"""
ProductRelation (master spec section 29) — a typed edge between two
Products in the same organization (alternative / complementary /
similar / frequently_bought_together / replacement).

Deliberately NOT reusing Phase 2's generic `Relationship` table, for
the same reason recorded in ADR-014 when Phase 5 declined to reuse it:
`Relationship` models KNOWLEDGE-graph edges (this entity contains that
compound), keyed by a `graph_node_type` enum already exercised by
Phases 2-6's tests. A product-catalogue edge is a different kind of
fact with a different, spec-given vocabulary (section 29's five types),
and altering that shared production enum for a Phase-7-only need was
judged riskier than a small, independently-scoped table. This one also
needs a `confidence` column that `Relationship` has no equivalent for.

`organization_id` added beyond section 29's literal field list, same
reasoning as Offer/ProductEvidence (ADR-022). Both FKs additionally
tenant-checked in the service layer before insert, so a relation can
never span two organizations.

Direction is meaningful and NOT auto-mirrored: "Product B is a
REPLACEMENT for Product A" does not imply the reverse (the discontinued
item is not a replacement for its successor). If a merchant wants a
symmetric relation they create both directions explicitly - the system
does not guess which of the five types happen to be symmetric.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, CheckConstraint, Enum as SAEnum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import ProductRelationType


class ProductRelation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_relations"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "related_product_id", "relation_type",
            name="uq_product_relations_product_related_type",
        ),
        CheckConstraint("product_id <> related_product_id", name="ck_product_relations_no_self_reference"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_product_relations_confidence_range",
        ),
    )

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    related_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type: Mapped[ProductRelationType] = mapped_column(
        SAEnum(ProductRelationType, name="product_relation_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # 0-1, nullable. NULL means "asserted by a human, no confidence
    # score attached" - which is different from 0.0 ("scored, and the
    # score is zero"). A future automated relation-inference job would
    # populate this; a merchant typing "these two go together" leaves
    # it NULL rather than being forced to invent a number.
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ProductRelation {self.product_id} -{self.relation_type.value}-> {self.related_product_id}>"
        )
