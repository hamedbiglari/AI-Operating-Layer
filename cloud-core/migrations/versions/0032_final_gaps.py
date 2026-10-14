"""Research query sets, evidence-completion tasks, new gap types, retry counters (ADR-111). Additive.

Revision ID: 0032
Revises: 0031
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)
OLD_MODES = ("gap_driven", "user_driven", "exploratory", "continuous")
COMPLETION_STATES = "'open', 'searching', 'awaiting_review', 'satisfied', 'blocked', 'abandoned'"


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def upgrade() -> None:
    # §12 — a saved, editable research query set (distinct from Phase 13 demand query clusters)
    op.create_table(
        "research_query_sets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("keyword_ids", postgresql.JSON()),
        sa.Column("extra_terms", postgresql.JSON()),
        sa.Column("mode", sa.String(20), nullable=False, server_default="agent"),
        sa.Column("boolean_query", sa.Text()),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
        sa.CheckConstraint("mode IN ('single', 'multi', 'exact', 'boolean', 'agent')", name="mode"),
        sa.UniqueConstraint("organization_id", "knowledge_object_id", "name", name="uq_research_query_set_name"),
    )
    # §16 — what is still missing, tracked until it is satisfied
    op.create_table(
        "evidence_completion_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("claim_id", UUID, sa.ForeignKey("claims.id", ondelete="SET NULL")),
        sa.Column("knowledge_gap_id", UUID, sa.ForeignKey("knowledge_gaps.id", ondelete="SET NULL")),
        sa.Column("research_question_id", UUID, sa.ForeignKey("research_questions.id", ondelete="SET NULL")),
        sa.Column("what_is_missing", sa.Text(), nullable=False),
        sa.Column("required_route", sa.String(30)),
        sa.Column("required_directness", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("satisfied_by_evidence_id", UUID, sa.ForeignKey("evidence.id", ondelete="SET NULL")),
        sa.Column("outcome_note", sa.Text()),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True)),
        *_ts(),
        sa.CheckConstraint(f"status IN ({COMPLETION_STATES})", name="status"),
        sa.CheckConstraint("required_directness IS NULL OR required_directness IN ('direct', 'indirect')", name="required_directness"),
        sa.CheckConstraint("status <> 'satisfied' OR satisfied_by_evidence_id IS NOT NULL", name="satisfied_needs_evidence"),
        sa.CheckConstraint("status NOT IN ('blocked', 'abandoned') OR outcome_note IS NOT NULL", name="a_dead_end_needs_a_reason"),
    )
    # §23 — gap types the prompt names
    for value in ("structure_gap", "retrieval_gap", "ux_gap", "commerce_gap"):
        op.execute(f"ALTER TYPE gap_type ADD VALUE IF NOT EXISTS '{value}'")
    # §32 — how many times a job had to retry
    op.add_column("ai_jobs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ai_jobs", sa.Column("switch_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("ai_jobs", "switch_count")
    op.drop_column("ai_jobs", "retry_count")
    # PostgreSQL cannot drop enum values; rows using the new gap types are moved to a kept value.
    op.execute("UPDATE knowledge_gaps SET gap_type = 'content_gap' "
               "WHERE gap_type::text IN ('structure_gap', 'retrieval_gap', 'ux_gap', 'commerce_gap')")
    op.drop_table("evidence_completion_tasks")
    op.drop_table("research_query_sets")
