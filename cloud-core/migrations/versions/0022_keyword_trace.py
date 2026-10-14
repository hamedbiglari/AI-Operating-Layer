"""
Keyword traceability chain (REQ-KW-004) and background task type on AI jobs
(ADR-095 worker enforcement). Explicit, queryable chain from keyword to
published content. Unreleased when written; additive only.

Revision ID: 0022
Revises: 0021
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "keyword_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_keywords.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False, server_default="keyword"),
        sa.Column("research_task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("claims.id", ondelete="SET NULL"), nullable=True),
        sa.Column("knowledge_object_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_objects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("knowledge_version_id", sa.Integer(), nullable=True),
        sa.Column("published_target", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "keyword_id", "research_task_id",
                            name="uq_keyword_trace_keyword_task"),
    )
    op.create_index("ix_keyword_traces_org", "keyword_traces", ["organization_id"])
    op.create_index("ix_keyword_traces_keyword", "keyword_traces", ["keyword_id"])
    # ADR-095: a job with a task type is background work and obeys BackgroundTaskPolicy.
    op.add_column("ai_jobs", sa.Column("task_type", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_jobs", "task_type")
    op.drop_index("ix_keyword_traces_keyword", table_name="keyword_traces")
    op.drop_index("ix_keyword_traces_org", table_name="keyword_traces")
    op.drop_table("keyword_traces")
