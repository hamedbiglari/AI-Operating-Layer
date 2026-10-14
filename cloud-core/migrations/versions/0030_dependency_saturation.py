"""Source dependency graph + research saturation (ADR-109). Additive.

Revision ID: 0030
Revises: 0029
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)
RELATIONS = "'cites', 'reviews', 'reanalyses', 'same_study', 'preprint_of', 'retracts', 'corrects'"
REASONS = ("'query_variants_exhausted', 'low_marginal_yield', 'duplicate_sources_only', 'budget_reached', "
           "'user_limit_reached', 'no_new_relevant_evidence', 'provider_unavailable', 'not_saturated'")


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def upgrade() -> None:
    # --- which source depends on which (a review on the trials it summarises) ---
    op.create_table(
        "source_dependencies",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_id", UUID, sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("depends_on_source_id", UUID, sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("relation", sa.String(20), nullable=False),
        sa.Column("detected_by", sa.String(20), nullable=False, server_default="user"),   # user | doi_reference | provider
        sa.Column("note", sa.Text()),
        *_ts(),
        sa.CheckConstraint(f"relation IN ({RELATIONS})", name="relation"),
        sa.CheckConstraint("detected_by IN ('user', 'doi_reference', 'provider')", name="detected_by"),
        sa.CheckConstraint("source_id <> depends_on_source_id", name="no_self_dependency"),
        sa.UniqueConstraint("organization_id", "source_id", "depends_on_source_id", "relation", name="uq_source_dependency"),
    )
    # --- one research iteration: what it cost and what it yielded ---
    op.create_table(
        "research_iterations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("research_question_id", UUID, sa.ForeignKey("research_questions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("route", sa.String(30), nullable=False),
        sa.Column("research_query_id", UUID, sa.ForeignKey("research_queries.id", ondelete="SET NULL")),
        sa.Column("sources_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("providers_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("providers_failed", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
        sa.UniqueConstraint("organization_id", "research_question_id", "iteration", name="uq_research_iteration"),
    )
    # --- the honest stopping decision ---
    op.add_column("research_questions", sa.Column("saturation_reason", sa.String(40)))
    op.add_column("research_questions", sa.Column("saturation_at", sa.TIMESTAMP(timezone=True)))
    op.add_column("research_questions", sa.Column("max_iterations", sa.Integer(), nullable=False, server_default="12"))
    op.create_check_constraint("saturation_reason", "research_questions",
                               f"saturation_reason IS NULL OR saturation_reason IN ({REASONS})")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_research_questions_saturation_reason"), "research_questions", type_="check")
    for c in ("max_iterations", "saturation_at", "saturation_reason"):
        op.drop_column("research_questions", c)
    op.drop_table("research_iterations")
    op.drop_table("source_dependencies")
