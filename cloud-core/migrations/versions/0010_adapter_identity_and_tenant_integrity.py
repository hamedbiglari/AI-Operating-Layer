"""installations, installation_credentials, wordpress_mappings + composite tenant FK hardening (Phase 9)

Revision ID: 0010
Revises: 0009
Create Date: 2026-01-10 00:00:00

Two distinct pieces of work, deliberately in one migration because the
second is a precondition for doing the first correctly:

**1. Adapter identity & mapping (master spec sections 38/39)** —
`installations`, `installation_credentials`, `wordpress_mappings`.

**2. Composite tenant FK hardening (ADR-037)** — closes the
long-standing gap recorded since Phase 5 and deferred twice: children
carried `organization_id` and a parent FK as two INDEPENDENT
constraints, so the database could not reject
`Offer.organization_id != Product.organization_id`. Only the service
layer could.

Adding `wordpress_mappings` with that same defect would have been a
fifth instance of a known bug, so it is closed here for the
non-polymorphic relationships, and the new table is born correct.

Technique: add `UNIQUE (id, organization_id)` to each parent (a no-op
constraint semantically, since `id` is already unique - it exists only
to be a composite FK target), then replace each child's single-column
FK with a composite one.

**Explicitly NOT covered**, and why: `trust_records.subject_id`,
`research_task_references.reference_id`, and
`wordpress_mappings.object_id` are polymorphic - they point at one of
several tables depending on a type column, and SQL has no FK for that.
Those remain service-enforced, which is documented rather than
pretended away.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (child_table, [child_cols], parent_table, [parent_cols], old_fk_name, new_fk_name, ondelete)
_COMPOSITE_FKS = [
    ("offers", ["product_id", "organization_id"], "products", ["id", "organization_id"],
     "fk_offers_product_id_products", "fk_offers_product_organization", "CASCADE"),
    ("product_evidence", ["product_id", "organization_id"], "products", ["id", "organization_id"],
     "fk_product_evidence_product_id_products", "fk_product_evidence_product_organization", "CASCADE"),
    ("product_evidence", ["evidence_id", "organization_id"], "evidence", ["id", "organization_id"],
     "fk_product_evidence_evidence_id_evidence", "fk_product_evidence_evidence_organization", "CASCADE"),
    ("product_relations", ["product_id", "organization_id"], "products", ["id", "organization_id"],
     "fk_product_relations_product_id_products", "fk_product_relations_product_organization", "CASCADE"),
    ("product_relations", ["related_product_id", "organization_id"], "products", ["id", "organization_id"],
     "fk_product_relations_related_product_id_products", "fk_product_relations_related_organization", "CASCADE"),
    ("recommendations", ["product_id", "organization_id"], "products", ["id", "organization_id"],
     "fk_recommendations_product_id_products", "fk_recommendations_product_organization", "CASCADE"),
    ("recommendations", ["offer_id", "organization_id"], "offers", ["id", "organization_id"],
     "fk_recommendations_offer_id_offers", "fk_recommendations_offer_organization", "SET NULL"),
    ("recommendations", ["customer_context_id", "organization_id"], "customer_contexts", ["id", "organization_id"],
     "fk_recommendations_customer_context_id_customer_contexts",
     "fk_recommendations_customer_context_organization", "SET NULL"),
]

_PARENT_UNIQUES = [
    ("products", "uq_products_id_organization_id"),
    ("evidence", "uq_evidence_id_organization_id"),
    ("offers", "uq_offers_id_organization_id"),
    ("customer_contexts", "uq_customer_contexts_id_organization_id"),
    ("sites", "uq_sites_id_organization_id"),
]


def upgrade() -> None:
    bind = op.get_bind()

    adapter_type = postgresql.ENUM(
        "wordpress", "rest", "mcp", "other", name="adapter_type", create_type=False)
    installation_status = postgresql.ENUM(
        "active", "suspended", "revoked", name="installation_status", create_type=False)
    credential_status = postgresql.ENUM(
        "active", "rotated", "revoked", name="credential_status", create_type=False)
    mapped_object_type = postgresql.ENUM(
        "knowledge_object", "product", name="mapped_object_type", create_type=False)
    sync_status = postgresql.ENUM(
        "pending", "synced", "stale", "failed", name="sync_status", create_type=False)
    for t in (adapter_type, installation_status, credential_status, mapped_object_type, sync_status):
        t.create(bind, checkfirst=True)

    # --- 1. Parent-side composite uniques (FK targets) -----------------
    for table, name in _PARENT_UNIQUES:
        op.create_unique_constraint(name, table, ["id", "organization_id"])

    # --- 2. installations / credentials ---------------------------------
    op.create_table(
        "installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("adapter_type", adapter_type, nullable=False),
        sa.Column("status", installation_status, nullable=False, server_default="active"),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
                                name="fk_installations_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
                                name="fk_installations_site_organization", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_installations"),
        sa.UniqueConstraint("id", "organization_id", name="uq_installations_id_organization_id"),
    )
    op.create_index("ix_installations_organization_id", "installations", ["organization_id"])
    op.create_index("ix_installations_site_id", "installations", ["site_id"])
    op.create_index("ix_installations_adapter_type", "installations", ["adapter_type"])
    op.create_index("ix_installations_status", "installations", ["status"])

    op.create_table(
        "installation_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("secret_hash", sa.String(length=255), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(length=64)), nullable=False, server_default="{}"),
        sa.Column("status", credential_status, nullable=False, server_default="active"),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rotated_from_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
                                name="fk_installation_credentials_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["installation_id", "organization_id"],
                                ["installations.id", "installations.organization_id"],
                                name="fk_installation_credentials_installation_organization", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rotated_from_id"], ["installation_credentials.id"],
                                name="fk_installation_credentials_rotated_from", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_installation_credentials"),
        sa.UniqueConstraint("key_id", name="uq_installation_credentials_key_id"),
    )
    op.create_index("ix_installation_credentials_organization_id", "installation_credentials", ["organization_id"])
    op.create_index("ix_installation_credentials_installation_id", "installation_credentials", ["installation_id"])
    op.create_index("ix_installation_credentials_key_id", "installation_credentials", ["key_id"])
    op.create_index("ix_installation_credentials_status", "installation_credentials", ["status"])

    # --- 3. wordpress_mappings ---------------------------------------------
    op.create_table(
        "wordpress_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("object_type", mapped_object_type, nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wordpress_post_id", sa.Integer(), nullable=False),
        sa.Column("wordpress_post_type", sa.Text(), nullable=True),
        sa.Column("wordpress_url", sa.Text(), nullable=True),
        sa.Column("sync_status", sync_status, nullable=False, server_default="pending"),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("remote_updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
                                name="fk_wordpress_mappings_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
                                name="fk_wordpress_mappings_site_organization", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["installation_id", "organization_id"],
                                ["installations.id", "installations.organization_id"],
                                name="fk_wordpress_mappings_installation_organization", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_wordpress_mappings"),
        sa.UniqueConstraint("site_id", "object_type", "object_id", name="uq_wordpress_mappings_site_object"),
        sa.UniqueConstraint("site_id", "wordpress_post_id", name="uq_wordpress_mappings_site_post"),
    )
    op.create_index("ix_wordpress_mappings_organization_id", "wordpress_mappings", ["organization_id"])
    op.create_index("ix_wordpress_mappings_site_id", "wordpress_mappings", ["site_id"])
    op.create_index("ix_wordpress_mappings_installation_id", "wordpress_mappings", ["installation_id"])
    op.create_index("ix_wordpress_mappings_object_id", "wordpress_mappings", ["object_id"])
    op.create_index("ix_wordpress_mappings_sync_status", "wordpress_mappings", ["sync_status"])

    # --- 4. Replace single-column FKs with composite ones (ADR-037) -------
    for child, child_cols, parent, parent_cols, old_name, new_name, ondelete in _COMPOSITE_FKS:
        op.drop_constraint(old_name, child, type_="foreignkey")
        op.create_foreign_key(new_name, child, parent, child_cols, parent_cols, ondelete=ondelete)


def downgrade() -> None:
    # Restore single-column FKs first, then drop the new tables, then
    # the parent uniques they depend on - strict reverse order.
    for child, child_cols, parent, parent_cols, old_name, new_name, ondelete in _COMPOSITE_FKS:
        op.drop_constraint(new_name, child, type_="foreignkey")
        op.create_foreign_key(old_name, child, parent, [child_cols[0]], [parent_cols[0]], ondelete=ondelete)

    for idx in ("ix_wordpress_mappings_sync_status", "ix_wordpress_mappings_object_id",
                "ix_wordpress_mappings_installation_id", "ix_wordpress_mappings_site_id",
                "ix_wordpress_mappings_organization_id"):
        op.drop_index(idx, table_name="wordpress_mappings")
    op.drop_table("wordpress_mappings")

    for idx in ("ix_installation_credentials_status", "ix_installation_credentials_key_id",
                "ix_installation_credentials_installation_id", "ix_installation_credentials_organization_id"):
        op.drop_index(idx, table_name="installation_credentials")
    op.drop_table("installation_credentials")

    for idx in ("ix_installations_status", "ix_installations_adapter_type",
                "ix_installations_site_id", "ix_installations_organization_id"):
        op.drop_index(idx, table_name="installations")
    op.drop_table("installations")

    for table, name in _PARENT_UNIQUES:
        op.drop_constraint(name, table, type_="unique")

    bind = op.get_bind()
    for name in ("sync_status", "mapped_object_type", "credential_status",
                 "installation_status", "adapter_type"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
