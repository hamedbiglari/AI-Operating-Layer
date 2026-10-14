"""
CommerceMapping (master spec section 40) — links a Cloud Core Product to a
WooCommerce product/variation on one site.

DIRECTION OF TRUTH, which is the whole reason this table is separate from
`products` (ADR-050):

    Core owns   : what the product IS, and whether it may be recommended
    WooCommerce owns: its own post/variation IDs, and the merchant's
                      operational price and stock

Those are different facts, and neither side overwrites the other's. A
WooCommerce price change updates the `Offer` (§27's separation earning its
keep again — price was never on Product), never the Product's identity,
status, evidence or trust. Nothing in this table can publish a product,
verify evidence, or change a recommendation.

`woo_variation_id` is nullable because a simple product has no variation.
When present, the pair (product, variation) is the real commerce identity —
which is why uniqueness is on the triple including it, not on
`woo_product_id` alone.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CommerceSyncStatus


class CommerceMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commerce_mappings"
    __table_args__ = (
        # One Woo product/variation maps to at most one Core product per
        # site. NULLS NOT DISTINCT is required so two simple products
        # (variation_id NULL) on the same site cannot both claim the same
        # woo_product_id - the default NULL-distinct behaviour would let
        # them.
        UniqueConstraint(
            "site_id", "woo_product_id", "woo_variation_id",
            name="uq_commerce_mappings_site_woo_product_variation",
            postgresql_nulls_not_distinct=True,
        ),
        UniqueConstraint(
            "site_id", "product_id", "woo_variation_id",
            name="uq_commerce_mappings_site_product_variation",
            postgresql_nulls_not_distinct=True,
        ),
        # Composite tenant FKs (ADR-037): the database itself refuses a
        # mapping whose site or product belongs to another organization.
        # The Phase 9 lesson applied at creation rather than retrofitted.
        ForeignKeyConstraint(
            ["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
            name="fk_commerce_mappings_site_organization", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "organization_id"], ["products.id", "products.organization_id"],
            name="fk_commerce_mappings_product_organization", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["installation_id", "organization_id"],
            ["installations.id", "installations.organization_id"],
            name="fk_commerce_mappings_installation_organization", ondelete="SET NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    installation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    woo_product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    woo_variation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The merchant's SKU as WooCommerce reports it. Recorded for
    # reconciliation and human diagnosis; NEVER used to resolve identity,
    # because SKUs are merchant-entered free text and collide.
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    sync_status: Mapped[CommerceSyncStatus] = mapped_column(
        SAEnum(CommerceSyncStatus, name="commerce_sync_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=CommerceSyncStatus.PENDING,
        server_default=CommerceSyncStatus.PENDING.value,
        index=True,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CommerceMapping product={self.product_id} -> woo {self.woo_product_id}"
            f"/{self.woo_variation_id} ({self.sync_status.value})>"
        )
