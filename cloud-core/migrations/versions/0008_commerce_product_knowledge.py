"""products, offers, product_evidence, product_relations, trust_records + deferred intents.product_id FK (Phase 7: Commerce & Product Knowledge)

Revision ID: 0008
Revises: 0007
Create Date: 2026-01-08 00:00:00

Phase 7: the commerce/product-knowledge foundation — `products`
(section 26, "a normalized Product Knowledge Object", not a WooCommerce
mirror), `offers` (section 27, kept deliberately separate from Product
so price/stock/seller/promotion can vary), `product_evidence`
(section 28, every link scoped to a specific stated claim),
`product_relations` (section 29), and `trust_records` (section 30,
evidence-backed with deliberately NO score column).

**This migration also closes the deferred FK on `intents.product_id`**,
honouring the commitment `app/models/intent.py` and migration `0007`
both recorded in writing ("a future Phase 7 migration adds
intents.product_id's FK the same way, via op.create_foreign_key, never
by editing this migration"). This is the identical pattern migration
`0004` used to close `relationships.source_id`'s deferred FK once
`sources` existed. Migration `0007` itself is NOT edited.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    product_status = postgresql.ENUM(
        "draft", "in_review", "published", "archived", name="product_status", create_type=False,
    )
    product_provenance = postgresql.ENUM(
        "merchant", "woocommerce", "supplier", "imported_document", "research", "external",
        name="product_provenance", create_type=False,
    )
    offer_availability = postgresql.ENUM(
        "in_stock", "out_of_stock", "preorder", "backorder", "discontinued",
        name="offer_availability", create_type=False,
    )
    offer_condition = postgresql.ENUM(
        "new", "used", "refurbished", name="offer_condition", create_type=False,
    )
    product_relation_type = postgresql.ENUM(
        "alternative", "complementary", "similar", "frequently_bought_together", "replacement",
        name="product_relation_type", create_type=False,
    )
    verification_status = postgresql.ENUM(
        "unverified", "pending_review", "verified", "rejected",
        name="verification_status", create_type=False,
    )
    trust_type = postgresql.ENUM(
        "business_identity", "supplier", "origin", "quality", "testing", "certification",
        "policy", "review", name="trust_type", create_type=False,
    )
    trust_subject_type = postgresql.ENUM(
        "organization", "product", "claim", name="trust_subject_type", create_type=False,
    )

    for enum_type in (
        product_status, product_provenance, offer_availability, offer_condition,
        product_relation_type, verification_status, trust_type, trust_subject_type,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- products ---------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("origin", sa.String(length=255), nullable=True),
        sa.Column("ingredients", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("specifications", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("certifications", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("images", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("shipping", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("returns_policy", sa.Text(), nullable=True),
        sa.Column("status", product_status, nullable=False, server_default="draft"),
        sa.Column("provenance", product_provenance, nullable=False, server_default="merchant"),
        sa.Column("knowledge_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_products_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"], ["sites.id"], name="fk_products_site_id_sites", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_object_id"], ["knowledge_objects.id"],
            name="fk_products_knowledge_object_id_knowledge_objects", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("organization_id", "sku", name="uq_products_organization_sku"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_products_organization_slug"),
    )
    op.create_index("ix_products_organization_id", "products", ["organization_id"])
    op.create_index("ix_products_site_id", "products", ["site_id"])
    op.create_index("ix_products_external_id", "products", ["external_id"])
    op.create_index("ix_products_sku", "products", ["sku"])
    op.create_index("ix_products_brand", "products", ["brand"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_status", "products", ["status"])
    op.create_index("ix_products_knowledge_object_id", "products", ["knowledge_object_id"])

    # --- offers -------------------------------------------------------
    op.create_table(
        "offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("availability", offer_availability, nullable=False, server_default="in_stock"),
        sa.Column("stock_quantity", sa.Integer(), nullable=True),
        sa.Column("condition", offer_condition, nullable=False, server_default="new"),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_offers_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_offers_product_id_products", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_offers"),
        sa.CheckConstraint("price IS NULL OR price >= 0", name="ck_offers_price_non_negative"),
        sa.CheckConstraint(
            "stock_quantity IS NULL OR stock_quantity >= 0", name="ck_offers_stock_quantity_non_negative"
        ),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_until IS NULL OR valid_until > valid_from",
            name="ck_offers_validity_window_ordered",
        ),
    )
    op.create_index("ix_offers_organization_id", "offers", ["organization_id"])
    op.create_index("ix_offers_product_id", "offers", ["product_id"])
    op.create_index("ix_offers_external_id", "offers", ["external_id"])
    op.create_index("ix_offers_availability", "offers", ["availability"])

    # --- product_evidence -----------------------------------------------
    op.create_table(
        "product_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("verification_status", verification_status, nullable=False, server_default="unverified"),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_product_evidence_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"],
            name="fk_product_evidence_product_id_products", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"],
            name="fk_product_evidence_evidence_id_evidence", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_evidence"),
        sa.UniqueConstraint(
            "product_id", "evidence_id", "claim", name="uq_product_evidence_product_evidence_claim"
        ),
    )
    op.create_index("ix_product_evidence_organization_id", "product_evidence", ["organization_id"])
    op.create_index("ix_product_evidence_product_id", "product_evidence", ["product_id"])
    op.create_index("ix_product_evidence_evidence_id", "product_evidence", ["evidence_id"])
    op.create_index("ix_product_evidence_verification_status", "product_evidence", ["verification_status"])

    # --- product_relations ------------------------------------------------
    op.create_table(
        "product_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("related_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", product_relation_type, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_product_relations_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"],
            name="fk_product_relations_product_id_products", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["related_product_id"], ["products.id"],
            name="fk_product_relations_related_product_id_products", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_relations"),
        sa.UniqueConstraint(
            "product_id", "related_product_id", "relation_type",
            name="uq_product_relations_product_related_type",
        ),
        sa.CheckConstraint("product_id <> related_product_id", name="ck_product_relations_no_self_reference"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_product_relations_confidence_range",
        ),
    )
    op.create_index("ix_product_relations_organization_id", "product_relations", ["organization_id"])
    op.create_index("ix_product_relations_product_id", "product_relations", ["product_id"])
    op.create_index("ix_product_relations_related_product_id", "product_relations", ["related_product_id"])

    # --- trust_records ------------------------------------------------------
    op.create_table(
        "trust_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", trust_subject_type, nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trust_type", trust_type, nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verification_status", verification_status, nullable=False, server_default="unverified"),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_trust_records_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"],
            name="fk_trust_records_evidence_id_evidence", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trust_records"),
    )
    op.create_index("ix_trust_records_organization_id", "trust_records", ["organization_id"])
    op.create_index("ix_trust_records_subject_id", "trust_records", ["subject_id"])
    op.create_index("ix_trust_records_trust_type", "trust_records", ["trust_type"])
    op.create_index("ix_trust_records_evidence_id", "trust_records", ["evidence_id"])
    op.create_index("ix_trust_records_verification_status", "trust_records", ["verification_status"])

    # --- close the deferred intents.product_id FK (see module docstring) ---
    op.create_foreign_key(
        "fk_intents_product_id_products", "intents", "products", ["product_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_intents_product_id_products", "intents", type_="foreignkey")

    op.drop_index("ix_trust_records_verification_status", table_name="trust_records")
    op.drop_index("ix_trust_records_evidence_id", table_name="trust_records")
    op.drop_index("ix_trust_records_trust_type", table_name="trust_records")
    op.drop_index("ix_trust_records_subject_id", table_name="trust_records")
    op.drop_index("ix_trust_records_organization_id", table_name="trust_records")
    op.drop_table("trust_records")

    op.drop_index("ix_product_relations_related_product_id", table_name="product_relations")
    op.drop_index("ix_product_relations_product_id", table_name="product_relations")
    op.drop_index("ix_product_relations_organization_id", table_name="product_relations")
    op.drop_table("product_relations")

    op.drop_index("ix_product_evidence_verification_status", table_name="product_evidence")
    op.drop_index("ix_product_evidence_evidence_id", table_name="product_evidence")
    op.drop_index("ix_product_evidence_product_id", table_name="product_evidence")
    op.drop_index("ix_product_evidence_organization_id", table_name="product_evidence")
    op.drop_table("product_evidence")

    op.drop_index("ix_offers_availability", table_name="offers")
    op.drop_index("ix_offers_external_id", table_name="offers")
    op.drop_index("ix_offers_product_id", table_name="offers")
    op.drop_index("ix_offers_organization_id", table_name="offers")
    op.drop_table("offers")

    op.drop_index("ix_products_knowledge_object_id", table_name="products")
    op.drop_index("ix_products_status", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_brand", table_name="products")
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_index("ix_products_external_id", table_name="products")
    op.drop_index("ix_products_site_id", table_name="products")
    op.drop_index("ix_products_organization_id", table_name="products")
    op.drop_table("products")

    bind = op.get_bind()
    postgresql.ENUM(name="trust_subject_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="trust_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="verification_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="product_relation_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="offer_condition").drop(bind, checkfirst=True)
    postgresql.ENUM(name="offer_availability").drop(bind, checkfirst=True)
    postgresql.ENUM(name="product_provenance").drop(bind, checkfirst=True)
    postgresql.ENUM(name="product_status").drop(bind, checkfirst=True)
