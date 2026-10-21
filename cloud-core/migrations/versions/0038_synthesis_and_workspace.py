"""Budgeted synthesis with a per-unit coverage ledger (ADR-124) and the persistent command workspace
(ADR-125). Additive and reversible.

Revision ID: 0038
Revises: 0037
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSON()

RUN_STATUSES = ("planned", "blocked", "queued", "running", "completed", "completed_with_gaps", "failed", "cancelled")
UNIT_STATUSES = ("pending", "processed", "represented", "merged", "transformed", "unresolved", "contradictory",
                 "omitted")
COMMAND_STATES = ("draft", "queued", "running", "completed", "completed_with_gaps", "blocked", "failed", "cancelled")
INTENTS = ("evidence_research", "synthesis", "find_evidence_for_claim", "contradictions", "section_applicability",
           "matrix_cell_research", "reprocess_document", "claims_from_page", "unsupported_statements",
           "coverage_audit", "continue_previous", "unknown")


def _q(v):
    return ", ".join(f"'{x}'" for x in v)


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "synthesis_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True),
        sa.Column("section_key", sa.String(100)),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("scope", JSON, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("budgets", JSON, nullable=False),
        sa.Column("plan", JSON),
        sa.Column("allow_partial", sa.Boolean(), nullable=False),
        sa.Column("policy_id", UUID),
        sa.Column("current_stage", sa.String(30)),
        sa.Column("ai_job_keys", JSON, nullable=False),
        sa.Column("knowledge_version", sa.Integer()),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("result_text", sa.Text()),
        sa.Column("audit", JSON),
        *[sa.Column(f"{n}_units", sa.Integer(), nullable=False, server_default="0")
          for n in ("input", "represented", "merged", "transformed", "unresolved", "contradictory", "omitted", "pending")],
        sa.Column("information_loss_rate", sa.Float()),
        sa.Column("publication_id", UUID, sa.ForeignKey("publications.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        *_ts(),
        sa.CheckConstraint(f"status IN ({_q(RUN_STATUSES)})", name="status"),
        sa.CheckConstraint("status NOT IN ('failed', 'blocked') OR failure_reason IS NOT NULL",
                           name="a_failure_needs_a_reason"),
        sa.CheckConstraint("status <> 'completed' OR (omitted_units = 0 AND pending_units = 0)",
                           name="complete_means_nothing_lost"),
    )
    op.create_table(
        "synthesis_units",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("run_id", UUID, sa.ForeignKey("synthesis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_key", sa.Integer(), nullable=False),
        sa.Column("claim_id", UUID, sa.ForeignKey("claims.id", ondelete="SET NULL"), index=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("pack_index", sa.Integer()),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("scores", JSON, nullable=False),
        sa.Column("contested", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("merged_into_key", sa.Integer()),
        sa.Column("omission_reason", sa.Text()),
        sa.Column("status_reason", sa.Text()),
        sa.Column("evidence_ids", JSON, nullable=False),
        sa.Column("source_ids", JSON, nullable=False),
        *_ts(),
        sa.CheckConstraint(f"status IN ({_q(UNIT_STATUSES)})", name="status"),
        sa.CheckConstraint("status <> 'omitted' OR omission_reason IS NOT NULL", name="an_omission_needs_a_reason"),
        sa.CheckConstraint("status <> 'merged' OR merged_into_key IS NOT NULL", name="a_merge_needs_a_target"),
        sa.UniqueConstraint("run_id", "unit_key", name="uq_synthesis_unit_key"),
    )
    op.create_index("ix_synthesis_units_run_status", "synthesis_units", ["run_id", "status"])

    op.create_table(
        "workspace_commands",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(300)),
        sa.Column("category_id", UUID, sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="SET NULL"), index=True),
        sa.Column("state", sa.String(30), nullable=False, index=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("last_executed_version", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_activity_at", sa.TIMESTAMP(timezone=True)),
        *_ts(),
        sa.CheckConstraint(f"state IN ({_q(COMMAND_STATES)})", name="state"),
        sa.CheckConstraint("state NOT IN ('failed', 'blocked') OR error IS NOT NULL", name="a_failure_needs_a_reason"),
    )
    op.create_index("ix_workspace_commands_owner", "workspace_commands",
                    ["organization_id", "user_id", "archived_at", "updated_at"])
    op.create_table(
        "workspace_command_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("command_id", UUID, sa.ForeignKey("workspace_commands.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(40)),
        sa.Column("scope", JSON, nullable=False),
        sa.Column("selected_source_ids", JSON, nullable=False),
        sa.Column("attachments", JSON, nullable=False),
        sa.Column("model_config", JSON, nullable=False),
        sa.Column("budget", JSON, nullable=False),
        sa.Column("plan", JSON),
        sa.Column("execution_state", sa.String(30), nullable=False),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("result", JSON),
        sa.Column("error", sa.Text()),
        sa.Column("synthesis_run_id", UUID, sa.ForeignKey("synthesis_runs.id", ondelete="SET NULL")),
        sa.Column("sync_job_id", UUID),
        sa.Column("cost", JSON),
        *_ts(),
        sa.UniqueConstraint("command_id", "version", name="uq_workspace_command_version"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(f"intent IS NULL OR intent IN ({_q(INTENTS)})", name="intent"),
        sa.CheckConstraint(f"execution_state IN ({_q(COMMAND_STATES)})", name="execution_state"),
    )
    from app.models.workspace import TRIGGER_STATEMENTS
    for stmt in TRIGGER_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_workspace_versions_freeze ON workspace_command_versions")
    op.execute("DROP FUNCTION IF EXISTS workspace_versions_freeze_executed()")
    op.drop_table("workspace_command_versions")
    op.drop_index("ix_workspace_commands_owner", table_name="workspace_commands")
    op.drop_table("workspace_commands")
    op.drop_index("ix_synthesis_units_run_status", table_name="synthesis_units")
    op.drop_table("synthesis_units")
    op.drop_table("synthesis_runs")
