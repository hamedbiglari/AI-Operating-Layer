"""
Offer (master spec section 27) — the terms on which a Product can be
bought right now. Section 27 is emphatic: "Keep Product and Offer
separate. This is important for: price, availability, variants,
sellers, promotions, future marketplaces."

So price/currency/stock/validity live HERE, never on Product. One
Product can have many Offers simultaneously (different sellers,
different currencies, a promotional offer valid for a window alongside
the standard one) — which is precisely why a `price` column on Product
would have been wrong.

`organization_id` is added beyond section 27's literal field list.
Section 27 lists only `product_id`, which would make an Offer's tenant
reachable only by joining Products. Every other tenant-owned child
table in this codebase (KnowledgeVersion, DocumentChunk, ClaimEvidence,
ResearchTask, QueryProvenance...) carries its own `organization_id`
per section 8's blanket rule, so a query never has to join to
tenant-scope, and a service-layer tenant check never depends on a join
being remembered. `commerce_service` additionally validates this column
against the parent Product's actual organization_id before insert —
the same two-hop discipline established in Phase 3/4/5/6. See
docs/DECISIONS.md ADR-022.

Deliberately NOT here: any "is this the best offer" / "should we show
this" judgment. That is Phase 8 (Recommendation Engine) territory; an
Offer row states facts about purchasability, nothing more.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OfferAvailability, OfferCondition


class Offer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint("price IS NULL OR price >= 0", name="ck_offers_price_non_negative"),
        CheckConstraint(
            "stock_quantity IS NULL OR stock_quantity >= 0", name="ck_offers_stock_quantity_non_negative"
        ),
        CheckConstraint(
            "valid_from IS NULL OR valid_until IS NULL OR valid_until > valid_from",
            name="ck_offers_validity_window_ordered",
        ),
    )

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
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Nullable: "price on request" / "contact for quote" is a real,
    # honest state for wholesale and B2B products, and is different
    # from a price of zero. Numeric(12, 2), not float - money must
    # never be stored in binary floating point.
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    availability: Mapped[OfferAvailability] = mapped_column(
        SAEnum(OfferAvailability, name="offer_availability", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=OfferAvailability.IN_STOCK,
        server_default=OfferAvailability.IN_STOCK.value,
        index=True,
    )
    # Nullable and SEPARATE from `availability` on purpose: many
    # merchants know an item is in stock without tracking an exact
    # count. NULL means "quantity untracked", which is not the same as
    # 0 ("tracked, and there are none") - collapsing the two would
    # silently turn untracked stock into out-of-stock.
    stock_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    condition: Mapped[OfferCondition] = mapped_column(
        SAEnum(OfferCondition, name="offer_condition", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=OfferCondition.NEW,
        server_default=OfferCondition.NEW.value,
    )
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    valid_from: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="offers")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Offer id={self.id} product_id={self.product_id} availability={self.availability.value}>"
