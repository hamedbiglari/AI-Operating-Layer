"""Category schema, sections and the Master Topic Matrix (ADR-114). Additive.

`knowledge_objects.object_type` is deliberately left alone: nothing is migrated, nothing is rewritten,
and a Knowledge Object without a category behaves exactly as before.

Revision ID: 0033
Revises: 0032
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)

STATUSES = ("'documented', 'verified', 'partial', 'needs_research', 'field_research', 'experiment_required', "
            "'user_input', 'new', 'conflicting', 'outdated', 'processing', 'no_evidence_found', "
            "'not_applicable', 'error'")
ORIGINS = "'category_schema', 'discovered', 'user_added'"
PROP = "'pending', 'evaluated', 'skipped'"


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def _org():
    return sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_category_id", UUID, sa.ForeignKey("categories.id", ondelete="SET NULL")),
        *_ts(),
        sa.UniqueConstraint("organization_id", "slug", name="uq_categories_slug"),
        sa.CheckConstraint("schema_version >= 1", name="schema_version_positive"),
    )
    op.create_table(
        "section_definitions",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("category_id", UUID, sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("origin", sa.String(20), nullable=False, server_default="category_schema"),
        sa.Column("discovered_from_topic_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="SET NULL")),
        sa.Column("discovered_evidence_id", UUID, sa.ForeignKey("evidence.id", ondelete="SET NULL")),
        sa.Column("reviewed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        *_ts(),
        sa.UniqueConstraint("organization_id", "category_id", "key", name="uq_section_definition_key"),
        sa.CheckConstraint(f"origin IN ({ORIGINS})", name="origin"),
        sa.CheckConstraint("position >= 0", name="position_positive"),
    )
    op.create_table(
        "knowledge_sections",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("section_definition_id", UUID, sa.ForeignKey("section_definitions.id", ondelete="SET NULL")),
        sa.Column("section_key", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="needs_research"),
        sa.Column("last_good_status", sa.String(30)),
        sa.Column("rationale", sa.Text()),
        sa.Column("origin", sa.String(20), nullable=False, server_default="category_schema"),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("direct_evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gap_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("research_question_id", UUID, sa.ForeignKey("research_questions.id", ondelete="SET NULL")),
        sa.Column("knowledge_version", sa.Integer()),
        sa.Column("last_research_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_audited_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("metadata", postgresql.JSON()),
        *_ts(),
        sa.UniqueConstraint("organization_id", "knowledge_object_id", "section_key", name="uq_knowledge_section"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="status"),
        sa.CheckConstraint(f"origin IN ({ORIGINS})", name="origin"),
        sa.CheckConstraint("status <> 'error' OR last_good_status IS NOT NULL", name="error_keeps_last_good"),
        sa.CheckConstraint("status NOT IN ('not_applicable', 'no_evidence_found') OR rationale IS NOT NULL",
                           name="a_closed_cell_needs_a_reason"),
    )
    op.create_index("ix_knowledge_sections_status", "knowledge_sections", ["organization_id", "status"])
    op.create_table(
        "section_propagations",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("section_definition_id", UUID, sa.ForeignKey("section_definitions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("resulting_status", sa.String(30)),
        sa.Column("note", sa.Text()),
        sa.Column("decided_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True)),
        *_ts(),
        sa.UniqueConstraint("organization_id", "section_definition_id", "knowledge_object_id", name="uq_section_propagation"),
        sa.CheckConstraint(f"state IN ({PROP})", name="state"),
        sa.CheckConstraint("state <> 'skipped' OR note IS NOT NULL", name="skipping_needs_a_reason"),
    )
    # a claim records which section it belongs to, so a matrix cell is read from real claims
    op.add_column("claims", sa.Column("section_key", sa.String(100)))
    op.create_index("ix_claims_section_key", "claims", ["organization_id", "section_key"])

    # the existing topic table gains one nullable link; object_type is untouched
    op.add_column("knowledge_objects", sa.Column("category_id", UUID, sa.ForeignKey("categories.id", ondelete="SET NULL")))
    op.create_index("ix_knowledge_objects_category_id", "knowledge_objects", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_claims_section_key", table_name="claims")
    op.drop_column("claims", "section_key")
    op.drop_index("ix_knowledge_objects_category_id", table_name="knowledge_objects")
    op.drop_column("knowledge_objects", "category_id")
    op.drop_table("section_propagations")
    op.drop_index("ix_knowledge_sections_status", table_name="knowledge_sections")
    op.drop_table("knowledge_sections")
    op.drop_table("section_definitions")
    op.drop_table("categories")
