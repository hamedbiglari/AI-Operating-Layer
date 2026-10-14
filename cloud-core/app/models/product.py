"""
Product (master spec section 26) — deliberately NOT a WooCommerce
mirror. Section 26 states it plainly: "The product object is not merely
a WooCommerce mirror. It is a normalized Product Knowledge Object."

Two consequences that shape this model:

1. **Price and availability are NOT here.** Section 27 ("Keep Product
   and Offer separate") puts them on Offer, because the same product
   can have different price/stock/seller/promotion state. A Product row
   answers "what IS this thing"; an Offer row answers "on what terms
   can it be bought right now". `app/models/offer.py`.

2. **`status` follows the same DRAFT -> IN_REVIEW -> PUBLISHED ->
   ARCHIVED lifecycle as KnowledgeObject**, not an invented commerce
   lifecycle — a Product IS a knowledge object per section 26, so it
   gets the same never-auto-publish discipline (section 44).

Fields beyond section 26's literal list, each justified rather than
added by habit (see docs/DECISIONS.md ADR-021):

- `provenance` — the Phase 7 brief requires distinguishing merchant
  input from WooCommerce sync from supplier data, and requires that
  "not all information [be represented] as equally authoritative".
  Without this column that distinction is unrecoverable post-import.
- `slug` IS in the literal list; `organization_id`/`site_id` are too.
  `updated_at`/`created_at` come from TimestampMixin as everywhere else.

`ingredients`, `specifications`, `certifications`, `images`, and
`shipping` are JSONB rather than separate tables: section 26 names them
as product FIELDS, not as their own entities with their own lifecycles,
and their shape varies by product type (a herb's "ingredients" and a
device's "specifications" share no schema). Same rationale as
`Source.metadata_` (Phase 3). A future phase that needs to query
*inside* these (e.g. "every product certified organic") can add a
generated column or a separate index without a model change.

Knowledge linkage is deliberately a nullable FK to `knowledge_objects`,
NOT a copy of the Knowledge Object's content — the Phase 7 brief is
explicit: "Avoid copying the entire Knowledge Object into Product."
A Product about Taranjabin points at the Taranjabin KnowledgeObject;
it does not restate its claims.
"""

import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProductProvenance, ProductStatus


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        # A merchant's SKU is unique within their own organization, not
        # globally - two different merchants can legitimately use the
        # same SKU string. Partial (WHERE sku IS NOT NULL) because sku
        # is optional: section 26 lists it, but not every product type
        # has one, and NULLs must not collide.
        UniqueConstraint("organization_id", "sku", name="uq_products_organization_sku"),
        UniqueConstraint("organization_id", "slug", name="uq_products_organization_slug"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional: a product may belong to a specific site, or to the
    # organization as a whole (a merchant with several storefronts
    # selling the same catalogue). SET NULL, not CASCADE - deleting a
    # storefront must not destroy the product knowledge behind it.
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The id this product carries in whatever system it came FROM
    # (WooCommerce post ID, supplier catalogue ref, ...). Not unique -
    # two different source systems can reuse the same external id.
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Open vocabularies - a merchant's brand/category taxonomy is their
    # own and must never require a migration to extend.
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    origin: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Section 26 names these as product FIELDS with product-type-
    # dependent shapes - see module docstring for why JSONB and not
    # separate tables.
    ingredients: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    specifications: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    certifications: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    images: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    shipping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    returns_policy: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ProductStatus.DRAFT,
        server_default=ProductStatus.DRAFT.value,
        index=True,
    )
    provenance: Mapped[ProductProvenance] = mapped_column(
        SAEnum(ProductProvenance, name="product_provenance", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ProductProvenance.MERCHANT,
        server_default=ProductProvenance.MERCHANT.value,
    )

    # A POINTER to knowledge, never a copy of it (see module docstring).
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_objects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    knowledge_object: Mapped["KnowledgeObject | None"] = relationship()  # noqa: F821
    offers: Mapped[list["Offer"]] = relationship(  # noqa: F821
        back_populates="product", cascade="all, delete-orphan"
    )
    evidence_links: Mapped[list["ProductEvidence"]] = relationship(  # noqa: F821
        back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Product id={self.id} name={self.name!r} status={self.status.value}>"
