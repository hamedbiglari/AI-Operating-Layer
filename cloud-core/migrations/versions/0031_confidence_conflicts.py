"""Extraction confidence separate from evidence strength, and first-class conflicts (ADR-110). Additive.

Revision ID: 0031
Revises: 0030
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)
CONFLICT_STATES = "'unreviewed', 'under_review', 'partially_resolved', 'resolved', 'unresolvable'"


def upgrade() -> None:
    # §19 — "how sure are we the source says X" is not "how strong is the science"
    op.add_column("evidence", sa.Column("extraction_confidence", sa.Numeric(4, 3)))
    op.add_column("evidence", sa.Column("extraction_note", sa.Text()))
    op.create_check_constraint("extraction_confidence_range", "evidence",
                               "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND extraction_confidence <= 1)")
    # a machine-read extraction may not claim certainty about what the source says
    op.create_check_constraint("machine_extraction_is_not_certain", "evidence",
                               "NOT source_generated OR human_reviewed OR extraction_confidence IS NULL OR extraction_confidence < 1")
    # §21 — a conflict is an object with the comparison, not a silent choice
    op.create_table(
        "evidence_conflicts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("claim_id", UUID, sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="SET NULL")),
        sa.Column("supporting_evidence_id", UUID, sa.ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contradicting_evidence_id", UUID, sa.ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="unreviewed"),
        sa.Column("comparison", postgresql.JSON()),          # population, intervention, dose, duration, design…
        sa.Column("resolution_note", sa.Text()),
        sa.Column("reviewed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({CONFLICT_STATES})", name="status"),
        sa.CheckConstraint("supporting_evidence_id <> contradicting_evidence_id", name="two_different_findings"),
        sa.CheckConstraint("status IN ('unreviewed', 'under_review') OR resolution_note IS NOT NULL",
                           name="a_decision_needs_a_reason"),
        sa.UniqueConstraint("organization_id", "claim_id", "supporting_evidence_id", "contradicting_evidence_id",
                            name="uq_evidence_conflict"),
    )


def downgrade() -> None:
    op.drop_table("evidence_conflicts")
    op.drop_constraint(op.f("ck_evidence_machine_extraction_is_not_certain"), "evidence", type_="check")
    op.drop_constraint(op.f("ck_evidence_extraction_confidence_range"), "evidence", type_="check")
    op.drop_column("evidence", "extraction_note")
    op.drop_column("evidence", "extraction_confidence")
