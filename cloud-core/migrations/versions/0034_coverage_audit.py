"""Coverage Audit — six dimensions, versioned, failure-safe (ADR-115). Additive.

Revision ID: 0034
Revises: 0033
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "coverage_audits",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True),
        sa.Column("category_id", UUID, sa.ForeignKey("categories.id", ondelete="CASCADE"), index=True),
        sa.Column("audit_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("knowledge_version", sa.Integer()),
        sa.Column("schema_version", sa.Integer()),
        sa.Column("trigger", sa.String(40)),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("dimensions", postgresql.JSON()),
        sa.Column("cross_topic", postgresql.JSON()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("scope IN ('topic', 'category', 'organization')", name="scope"),
        sa.CheckConstraint("status IN ('succeeded', 'failed', 'running')", name="status"),
        sa.CheckConstraint("status <> 'failed' OR failure_reason IS NOT NULL", name="a_failure_needs_a_reason"),
        sa.CheckConstraint("(scope = 'topic') = (knowledge_object_id IS NOT NULL)", name="topic_scope_needs_a_topic"),
        sa.CheckConstraint("(scope = 'category') = (category_id IS NOT NULL)", name="category_scope_needs_a_category"),
        sa.CheckConstraint("audit_version >= 1", name="audit_version_positive"),
        sa.UniqueConstraint("organization_id", "scope", "knowledge_object_id", "category_id", "audit_version",
                            name="uq_coverage_audit_version"),
    )
    op.create_index("ix_coverage_audits_latest", "coverage_audits",
                    ["organization_id", "scope", "status", "audit_version"])


def downgrade() -> None:
    op.drop_index("ix_coverage_audits_latest", table_name="coverage_audits")
    op.drop_table("coverage_audits")
