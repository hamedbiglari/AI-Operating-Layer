"""
Agent Orchestration Layer + Background Processing Policy + Memory Profiles
(ADR-095/096/097/098, 2026-09-25). Additive only.

Revision ID: 0021
Revises: 0020
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Background Task Policies --
    op.create_table("background_task_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("allowed_account_ids", postgresql.JSON, nullable=True),
        sa.Column("routing_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("routing_mode", sa.String(40), nullable=True),
        sa.Column("max_cost_per_run", sa.Numeric(18, 6), nullable=True),
        sa.Column("max_cost_currency", sa.String(10), nullable=True),
        sa.Column("required_capabilities", postgresql.JSON, nullable=True),
        sa.Column("auto_switch_on_failure", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("pause_on_cost_limit", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "task_type", name="uq_bg_policy_task_type"),
    )
    op.create_index("ix_bg_task_policies_org", "background_task_policies", ["organization_id"])

    # -- Memory Profiles --
    op.create_table("memory_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("namespace", sa.String(200), nullable=False),
        sa.Column("scope", sa.String(30), nullable=False, server_default="project"),
        sa.Column("semantic_backend", sa.String(30), nullable=False, server_default="native"),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_memory_profile_name"),
        sa.UniqueConstraint("organization_id", "namespace", name="uq_memory_profile_ns"),
    )
    op.create_index("ix_memory_profiles_org", "memory_profiles", ["organization_id"])

    # -- Agent Definitions --
    op.create_table("agent_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("protocol", sa.String(30), nullable=False, server_default="internal"),
        sa.Column("endpoint_url", sa.String(2048), nullable=True),
        sa.Column("auth_method", sa.String(30), nullable=True),
        sa.Column("trust_level", sa.String(20), nullable=False, server_default="tenant"),
        sa.Column("capabilities", postgresql.JSON, nullable=True),
        sa.Column("allowed_tools", postgresql.JSON, nullable=True),
        sa.Column("allowed_ai_accounts", postgresql.JSON, nullable=True),
        sa.Column("memory_profile_ids", postgresql.JSON, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_agent_definitions_name"),
    )
    op.create_index("ix_agent_definitions_org", "agent_definitions", ["organization_id"])

    # -- Agent Sessions --
    op.create_table("agent_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_key", sa.String(200), nullable=False),
        sa.Column("initiator_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("context", postgresql.JSON, nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "session_key", name="uq_agent_sessions_key"),
    )
    op.create_index("ix_agent_sessions_org", "agent_sessions", ["organization_id"])

    # -- Agent Tasks --
    op.create_table("agent_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("task_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_ref", postgresql.JSON, nullable=True),
        sa.Column("output_ref", postgresql.JSON, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("depends_on", postgresql.JSON, nullable=True),
        sa.Column("ai_execution_ids", postgresql.JSON, nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "session_id", "task_key", name="uq_agent_tasks_key"),
    )
    op.create_index("ix_agent_tasks_org_session", "agent_tasks", ["organization_id", "session_id"])

    # -- Agent Messages --
    op.create_table("agent_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("from_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_type", sa.String(50), nullable=False),
        sa.Column("payload_reference", postgresql.JSON, nullable=True),
        sa.Column("memory_references", postgresql.JSON, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="sent"),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_messages_org_session", "agent_messages", ["organization_id", "session_id"])

    # -- Agent Handoffs --
    op.create_table("agent_handoffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(100), nullable=True),
        sa.Column("working_memory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("package", postgresql.JSON, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_handoffs_org_session", "agent_handoffs", ["organization_id", "session_id"])

    # -- Agent Memory Bindings --
    op.create_table("agent_memory_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_level", sa.String(20), nullable=False, server_default="read"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "agent_definition_id", "memory_profile_id",
                            name="uq_agent_memory_binding"),
    )
    op.create_index("ix_agent_memory_bindings_org", "agent_memory_bindings", ["organization_id"])


def downgrade() -> None:
    for t in ["agent_memory_bindings", "agent_handoffs", "agent_messages", "agent_tasks",
              "agent_sessions", "agent_definitions", "memory_profiles", "background_task_policies"]:
        op.drop_table(t)
