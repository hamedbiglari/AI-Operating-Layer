"""research_projects, research_tasks, research_task_references (Phase 5: Research Engine)

Revision ID: 0006
Revises: 0005
Create Date: 2026-01-06 00:00:00

Phase 5: the Research Engine foundation — ResearchProject (a bounded
investigation, optionally driven by an existing Knowledge Gap) and
ResearchTask (one executable unit of work under a project, running
against the app/integrations/research/ ResearchProvider interface).
research_task_references is the small, Phase-5-scoped provenance link
table (see app/models/research_task_reference.py's docstring for why
this is a new table rather than reusing Relationship/graph_node_type).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    research_mode = postgresql.ENUM(
        "gap_driven", "user_driven", "exploratory", "continuous",
        name="research_mode", create_type=False,
    )
    research_project_status = postgresql.ENUM(
        "draft", "active", "completed", "cancelled", "archived",
        name="research_project_status", create_type=False,
    )
    research_task_status = postgresql.ENUM(
        "pending", "queued", "running", "completed", "failed", "cancelled",
        name="research_task_status", create_type=False,
    )
    research_reference_type = postgresql.ENUM(
        "source", "document", "evidence", "claim", "knowledge_object", "knowledge_gap",
        name="research_reference_type", create_type=False,
    )
    research_reference_role = postgresql.ENUM(
        "input", "output", name="research_reference_role", create_type=False,
    )

    for enum_type in (
        research_mode, research_project_status, research_task_status,
        research_reference_type, research_reference_role,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- research_projects --------------------------------------------
    op.create_table(
        "research_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("mode", research_mode, nullable=False),
        sa.Column("knowledge_gap_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", research_project_status, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_research_projects_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_gap_id"], ["knowledge_gaps.id"],
            name="fk_research_projects_knowledge_gap_id_knowledge_gaps", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_projects"),
        sa.CheckConstraint(
            "mode <> 'gap_driven' OR knowledge_gap_id IS NOT NULL",
            name="ck_research_projects_gap_driven_requires_gap",
        ),
    )
    op.create_index("ix_research_projects_organization_id", "research_projects", ["organization_id"])
    op.create_index("ix_research_projects_knowledge_gap_id", "research_projects", ["knowledge_gap_id"])

    # --- research_tasks ------------------------------------------------
    op.create_table(
        "research_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", research_task_status, nullable=False, server_default="pending"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_research_tasks_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_project_id"], ["research_projects.id"],
            name="fk_research_tasks_research_project_id_research_projects", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_tasks"),
    )
    op.create_index("ix_research_tasks_organization_id", "research_tasks", ["organization_id"])
    op.create_index("ix_research_tasks_research_project_id", "research_tasks", ["research_project_id"])
    op.create_index("ix_research_tasks_task_type", "research_tasks", ["task_type"])
    op.create_index("ix_research_tasks_status", "research_tasks", ["status"])

    # --- research_task_references ---------------------------------------
    op.create_table(
        "research_task_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_type", research_reference_type, nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", research_reference_role, nullable=False, server_default="output"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_research_task_references_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_task_id"], ["research_tasks.id"],
            name="fk_research_task_references_research_task_id_research_tasks", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_task_references"),
    )
    op.create_index("ix_research_task_references_organization_id", "research_task_references", ["organization_id"])
    op.create_index("ix_research_task_references_research_task_id", "research_task_references", ["research_task_id"])
    op.create_index("ix_research_task_references_reference_id", "research_task_references", ["reference_id"])


def downgrade() -> None:
    op.drop_index("ix_research_task_references_reference_id", table_name="research_task_references")
    op.drop_index("ix_research_task_references_research_task_id", table_name="research_task_references")
    op.drop_index("ix_research_task_references_organization_id", table_name="research_task_references")
    op.drop_table("research_task_references")

    op.drop_index("ix_research_tasks_status", table_name="research_tasks")
    op.drop_index("ix_research_tasks_task_type", table_name="research_tasks")
    op.drop_index("ix_research_tasks_research_project_id", table_name="research_tasks")
    op.drop_index("ix_research_tasks_organization_id", table_name="research_tasks")
    op.drop_table("research_tasks")

    op.drop_index("ix_research_projects_knowledge_gap_id", table_name="research_projects")
    op.drop_index("ix_research_projects_organization_id", table_name="research_projects")
    op.drop_table("research_projects")

    bind = op.get_bind()
    postgresql.ENUM(name="research_reference_role").drop(bind, checkfirst=True)
    postgresql.ENUM(name="research_reference_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="research_task_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="research_project_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="research_mode").drop(bind, checkfirst=True)
