"""Publication layer and sentence-level Vancouver citation (ADR-116). Additive.

Revision ID: 0035
Revises: 0034
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)
KINDS = "'factual', 'inference', 'interpretation', 'hypothesis', 'narrative', 'heading'"
SUPPORT = "'supports', 'partially_supports', 'background_only', 'unverified'"


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def _org():
    return sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("publication_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("knowledge_version", sa.Integer()),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sentence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        *_ts(),
        sa.CheckConstraint("status IN ('draft', 'resolving', 'resolved', 'published', 'superseded', 'failed')", name="status"),
        sa.CheckConstraint("status <> 'failed' OR failure_reason IS NOT NULL", name="a_failure_needs_a_reason"),
        sa.CheckConstraint("publication_version >= 1", name="version_positive"),
        sa.UniqueConstraint("organization_id", "knowledge_object_id", "publication_version", name="uq_publication_version"),
    )
    op.create_table(
        "publication_sections",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("publication_id", UUID, sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("section_key", sa.String(100)),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        *_ts(),
        sa.UniqueConstraint("publication_id", "position", name="uq_publication_section_position"),
    )
    op.create_table(
        "publication_sentences",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("publication_id", UUID, sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("publication_section_id", UUID, sa.ForeignKey("publication_sections.id", ondelete="CASCADE"), index=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("paragraph", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(20), nullable=False, server_default="factual"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("knowledge_unit_claim_id", UUID, sa.ForeignKey("claims.id", ondelete="SET NULL")),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_unavailable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("citation_numbers", postgresql.JSON()),
        sa.Column("citation_text", sa.String(300)),
        *_ts(),
        sa.CheckConstraint(f"kind IN ({KINDS})", name="kind"),
        sa.CheckConstraint("position >= 0", name="position_positive"),
        sa.CheckConstraint("NOT resolved OR kind NOT IN ('factual', 'inference', 'interpretation') "
                           "OR evidence_unavailable OR citation_numbers IS NOT NULL",
                           name="a_factual_sentence_needs_a_citation"),
        sa.UniqueConstraint("publication_id", "position", name="uq_publication_sentence_position"),
    )
    op.create_table(
        "sentence_sources",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("publication_sentence_id", UUID, sa.ForeignKey("publication_sentences.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_id", UUID, sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("claim_id", UUID, sa.ForeignKey("claims.id", ondelete="SET NULL")),
        sa.Column("evidence_id", UUID, sa.ForeignKey("evidence.id", ondelete="SET NULL")),
        sa.Column("support", sa.String(30), nullable=False, server_default="supports"),
        sa.Column("directness", sa.String(20)),
        sa.Column("note", sa.Text()),
        *_ts(),
        sa.CheckConstraint(f"support IN ({SUPPORT})", name="support"),
        sa.UniqueConstraint("publication_sentence_id", "source_id", name="uq_sentence_source"),
    )
    op.create_table(
        "publication_references",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("publication_id", UUID, sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_id", UUID, sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference_number", sa.Integer(), nullable=False),
        sa.Column("first_sentence_position", sa.Integer()),
        sa.Column("formatted", sa.Text()),
        sa.Column("source_kind", sa.String(50)),
        sa.Column("is_user_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("access_note", sa.String(200)),
        sa.Column("metadata", postgresql.JSON()),
        *_ts(),
        sa.CheckConstraint("reference_number >= 1", name="number_positive"),
        sa.UniqueConstraint("publication_id", "reference_number", name="uq_reference_number_per_publication"),
        sa.UniqueConstraint("publication_id", "source_id", name="uq_source_once_per_publication"),
    )


def downgrade() -> None:
    for t in ("publication_references", "sentence_sources", "publication_sentences",
              "publication_sections", "publications"):
        op.drop_table(t)
