"""Demand Intelligence: demand_connections + demand_signals (REQ-DI-001..003, ADR-099). Additive.

Revision ID: 0023
Revises: 0022
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCES = "'gsc', 'gsc_export', 'ga4', 'internal_search', 'ai_visibility', 'customer_query', 'product_behavior'"


def upgrade() -> None:
    op.create_table(
        "demand_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="NOT_CONNECTED"),
        sa.Column("property_ref", sa.String(500)),
        sa.Column("last_sync_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("imported_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "source_type", name="uq_demand_connection_source"),
        sa.CheckConstraint("source_type IN ('gsc', 'ga4')", name="ck_demand_connection_source"),
        sa.CheckConstraint("status IN ('NOT_CONNECTED', 'CONNECTED', 'ERROR', 'BLOCKED_EXTERNAL_DEPENDENCY')", name="ck_demand_connection_status"),
    )
    op.create_index("ix_demand_connections_organization_id", "demand_connections", ["organization_id"])
    op.create_table(
        "demand_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("dedupe_key", sa.String(600), nullable=False),
        sa.Column("query_text", sa.String(500), nullable=False),
        sa.Column("normalized_query", sa.String(500), nullable=False),
        sa.Column("impressions", sa.Integer()), sa.Column("clicks", sa.Integer()),
        sa.Column("ctr", sa.Numeric(8, 5)), sa.Column("position", sa.Numeric(8, 2)),
        sa.Column("page", sa.String(1000)), sa.Column("country", sa.String(10)), sa.Column("device", sa.String(20)),
        sa.Column("searches", sa.Integer()), sa.Column("zero_result_searches", sa.Integer()),
        sa.Column("period_start", sa.Date()), sa.Column("period_end", sa.Date()),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("raw", postgresql.JSON()),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("information_need", sa.Text()),
        sa.Column("research_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_tasks.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "source_type", "dedupe_key", name="uq_demand_signal_dedupe"),
        sa.CheckConstraint(f"source_type IN ({SOURCES})", name="ck_demand_signal_source"),
        sa.CheckConstraint("status IN ('new', 'promoted', 'dismissed')", name="ck_demand_signal_status"),
    )
    op.create_index("ix_demand_signals_organization_id", "demand_signals", ["organization_id"])
    op.create_index("ix_demand_signals_normalized_query", "demand_signals", ["normalized_query"])


def downgrade() -> None:
    op.drop_index("ix_demand_signals_normalized_query", table_name="demand_signals")
    op.drop_index("ix_demand_signals_organization_id", table_name="demand_signals")
    op.drop_table("demand_signals")
    op.drop_index("ix_demand_connections_organization_id", table_name="demand_connections")
    op.drop_table("demand_connections")
