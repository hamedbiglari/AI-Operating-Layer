"""visibility_tests, visibility_budgets (Phase 12: AI Visibility)

Revision ID: 0012
Revises: 0011
Create Date: 2026-01-12 00:00:00

Master spec §31.

Two notes on the shape:

1. The five section-31 signal columns are a tri-state ENUM
   (`signal_presence`), not booleans. A boolean `false` cannot distinguish
   "we looked and it was absent" from "we did not check", and a dashboard
   averaging those together is quietly wrong. See ADR-061.

2. `visibility_budgets` has no §31 mandate. It exists because Phase 12
   forensic reconciliation found no cost guard anywhere in the codebase,
   and Phase 12 is the first phase able to spend external money. ADR-063.

Both tables are born with composite tenant FKs (ADR-037).
No prior migration is modified.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    visibility_platform = postgresql.ENUM(
        "google", "bing", "chatgpt", "gemini", "perplexity", "copilot", "other",
        name="visibility_platform", create_type=False)
    visibility_test_type = postgresql.ENUM(
        "direct_query", "brand_query", "product_query", "comparison_query", "citation_check",
        name="visibility_test_type", create_type=False)
    signal_presence = postgresql.ENUM(
        "present", "absent", "not_checked", name="signal_presence", create_type=False)
    collection_method = postgresql.ENUM(
        "manual_paste", "platform_api", "automated_browser", "imported",
        name="visibility_collection_method", create_type=False)
    visibility_job_status = postgresql.ENUM(
        "queued", "running", "succeeded", "failed", "dead_letter", "cancelled", "budget_exceeded",
        name="visibility_job_status", create_type=False)
    for t in (visibility_platform, visibility_test_type, signal_presence,
              collection_method, visibility_job_status):
        t.create(bind, checkfirst=True)

    # Composite-FK target on `queries`. Migration 0010 added
    # UNIQUE (id, organization_id) to products/evidence/offers/
    # customer_contexts/sites, but not to queries - nothing needed it until
    # now. Semantically a no-op (id is already unique); it exists solely so
    # visibility_tests can carry a composite tenant FK rather than two
    # independent ones. Same technique and rationale as ADR-037.
    op.create_unique_constraint(
        "uq_queries_id_organization_id", "queries", ["id", "organization_id"]
    )

    op.create_table(
        "visibility_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("platform", visibility_platform, nullable=False),
        sa.Column("test_type", visibility_test_type, nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("mentioned", signal_presence, nullable=False, server_default="not_checked"),
        sa.Column("cited", signal_presence, nullable=False, server_default="not_checked"),
        sa.Column("recommended", signal_presence, nullable=False, server_default="not_checked"),
        sa.Column("product_present", signal_presence, nullable=False, server_default="not_checked"),
        sa.Column("url_present", signal_presence, nullable=False, server_default="not_checked"),
        sa.Column("collection_method", collection_method, nullable=False, server_default="manual_paste"),
        sa.Column("platform_model", sa.String(length=120), nullable=True),
        sa.Column("result_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("tested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(10, 6), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_visibility_tests_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id", "organization_id"],
            ["queries.id", "queries.organization_id"],
            name="fk_visibility_tests_query_organization", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id", "organization_id"],
            ["products.id", "products.organization_id"],
            name="fk_visibility_tests_product_organization", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_visibility_tests"),
    )
    for col in ("organization_id", "query_id", "product_id", "platform", "mentioned", "tested_at"):
        op.create_index(f"ix_visibility_tests_{col}", "visibility_tests", [col])

    op.create_table(
        "visibility_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_key", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("period_limit", sa.Numeric(10, 4), nullable=False),
        sa.Column("period_spent", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("last_reconciled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_visibility_budgets_organization_id_organizations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_visibility_budgets"),
        sa.UniqueConstraint("organization_id", "period_key", name="uq_visibility_budgets_org_period"),
        sa.CheckConstraint("period_limit >= 0", name="ck_visibility_budgets_limit_non_negative"),
        sa.CheckConstraint("period_spent >= 0", name="ck_visibility_budgets_spent_non_negative"),
    )
    op.create_index("ix_visibility_budgets_organization_id", "visibility_budgets", ["organization_id"])
    op.create_index("ix_visibility_budgets_period_key", "visibility_budgets", ["period_key"])


def downgrade() -> None:
    for col in ("period_key", "organization_id"):
        op.drop_index(f"ix_visibility_budgets_{col}", table_name="visibility_budgets")
    op.drop_table("visibility_budgets")

    for col in ("tested_at", "mentioned", "platform", "product_id", "query_id", "organization_id"):
        op.drop_index(f"ix_visibility_tests_{col}", table_name="visibility_tests")
    op.drop_table("visibility_tests")

    op.drop_constraint("uq_queries_id_organization_id", "queries", type_="unique")

    bind = op.get_bind()
    for name in ("visibility_job_status", "visibility_collection_method", "signal_presence",
                 "visibility_test_type", "visibility_platform"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
