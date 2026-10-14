"""commerce_mappings, sync_jobs (Phase 10: WooCommerce adapter)

Revision ID: 0011
Revises: 0010
Create Date: 2026-01-11 00:00:00

Master spec §40 (commerce_mappings) and §41 (sync_jobs).

Both tables are born with composite tenant foreign keys (ADR-037) rather
than acquiring them in a later hardening pass - the Phase 9 lesson applied
at creation. No prior migration is modified.

`NULLS NOT DISTINCT` on the commerce uniqueness constraints is load-bearing:
`woo_variation_id` is NULL for simple products, and Postgres' default
NULL-distinct behaviour would let two simple products on one site both claim
the same `woo_product_id`. Requires PostgreSQL 15+.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    commerce_sync_status = postgresql.ENUM(
        "pending", "synced", "stale", "failed", name="commerce_sync_status", create_type=False)
    sync_job_type = postgresql.ENUM(
        "commerce_product_sync", "commerce_offer_sync", "content_mapping_sync",
        name="sync_job_type", create_type=False)
    sync_job_status = postgresql.ENUM(
        "queued", "running", "succeeded", "failed", "dead_letter", "cancelled",
        name="sync_job_status", create_type=False)
    for t in (commerce_sync_status, sync_job_type, sync_job_status):
        t.create(bind, checkfirst=True)

    op.create_table(
        "commerce_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("woo_product_id", sa.Integer(), nullable=False),
        sa.Column("woo_variation_id", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("sync_status", commerce_sync_status, nullable=False, server_default="pending"),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_commerce_mappings_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
            name="fk_commerce_mappings_site_organization", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id", "organization_id"], ["products.id", "products.organization_id"],
            name="fk_commerce_mappings_product_organization", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["installation_id", "organization_id"],
            ["installations.id", "installations.organization_id"],
            name="fk_commerce_mappings_installation_organization", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_commerce_mappings"),
    )
    # NULLS NOT DISTINCT is not expressible through sa.UniqueConstraint in
    # this SQLAlchemy version, so the constraints are created explicitly.
    op.execute(
        "ALTER TABLE commerce_mappings ADD CONSTRAINT uq_commerce_mappings_site_woo_product_variation "
        "UNIQUE NULLS NOT DISTINCT (site_id, woo_product_id, woo_variation_id)"
    )
    op.execute(
        "ALTER TABLE commerce_mappings ADD CONSTRAINT uq_commerce_mappings_site_product_variation "
        "UNIQUE NULLS NOT DISTINCT (site_id, product_id, woo_variation_id)"
    )
    for col in ("organization_id", "site_id", "product_id", "installation_id", "sku", "sync_status"):
        op.create_index(f"ix_commerce_mappings_{col}", "commerce_mappings", [col])

    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", sync_job_type, nullable=False),
        sa.Column("status", sync_job_status, nullable=False, server_default="queued"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_sync_jobs_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
            name="fk_sync_jobs_site_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_sync_jobs"),
        sa.CheckConstraint("attempts >= 0", name="ck_sync_jobs_attempts_non_negative"),
        sa.UniqueConstraint("organization_id", "idempotency_key",
                            name="uq_sync_jobs_organization_idempotency_key"),
    )
    for col in ("organization_id", "site_id", "job_type", "status", "idempotency_key"):
        op.create_index(f"ix_sync_jobs_{col}", "sync_jobs", [col])


def downgrade() -> None:
    for col in ("idempotency_key", "status", "job_type", "site_id", "organization_id"):
        op.drop_index(f"ix_sync_jobs_{col}", table_name="sync_jobs")
    op.drop_table("sync_jobs")

    for col in ("sync_status", "sku", "installation_id", "product_id", "site_id", "organization_id"):
        op.drop_index(f"ix_commerce_mappings_{col}", table_name="commerce_mappings")
    op.drop_table("commerce_mappings")

    bind = op.get_bind()
    for name in ("sync_job_status", "sync_job_type", "commerce_sync_status"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
