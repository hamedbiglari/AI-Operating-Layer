"""evidence, claim_evidence (Phase 4: Evidence & Claim/Evidence linking)

Revision ID: 0005
Revises: 0004
Create Date: 2026-01-05 00:00:00

Phase 4: Evidence (a specific, citable finding drawn from a Source and
optionally pinned to a Document/DocumentChunk) plus claim_evidence (the
many-to-many link between Claim and Evidence that finally connects
Claims to the Sources/Documents built in Phase 3, and carries the
`relation` field the "Conflict foundations" aggregate logic in
app/services/claim_evidence_service.py reads).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    evidence_directness = postgresql.ENUM(
        "direct", "indirect", name="evidence_directness", create_type=False,
    )
    evidence_strength = postgresql.ENUM(
        "very_low", "low", "moderate", "high", name="evidence_strength", create_type=False,
    )
    evidence_status = postgresql.ENUM(
        "draft", "pending_review", "verified", "rejected", name="evidence_status", create_type=False,
    )
    evidence_relation = postgresql.ENUM(
        "supports", "contradicts", "mixed", "neutral", name="evidence_relation", create_type=False,
    )

    evidence_directness.create(bind, checkfirst=True)
    evidence_strength.create(bind, checkfirst=True)
    evidence_status.create(bind, checkfirst=True)
    evidence_relation.create(bind, checkfirst=True)

    # --- evidence ---------------------------------------------------
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("study_type", sa.String(length=100), nullable=True),
        sa.Column("directness", evidence_directness, nullable=False, server_default="direct"),
        sa.Column("evidence_strength", evidence_strength, nullable=False, server_default="very_low"),
        sa.Column("status", evidence_status, nullable=False, server_default="draft"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("population", sa.String(length=500), nullable=True),
        sa.Column("source_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("human_reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_evidence_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"],
            name="fk_evidence_source_id_sources", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name="fk_evidence_document_id_documents", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_chunk_id"], ["document_chunks.id"],
            name="fk_evidence_document_chunk_id_document_chunks", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
        sa.CheckConstraint(
            "sample_size IS NULL OR sample_size >= 0", name="ck_evidence_sample_size_non_negative"
        ),
    )
    op.create_index("ix_evidence_organization_id", "evidence", ["organization_id"])
    op.create_index("ix_evidence_source_id", "evidence", ["source_id"])
    op.create_index("ix_evidence_document_id", "evidence", ["document_id"])
    op.create_index("ix_evidence_document_chunk_id", "evidence", ["document_chunk_id"])
    op.create_index("ix_evidence_study_type", "evidence", ["study_type"])

    # --- claim_evidence -----------------------------------------------
    op.create_table(
        "claim_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation", evidence_relation, nullable=False, server_default="supports"),
        sa.Column("weight", sa.Numeric(3, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_claim_evidence_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["claims.id"],
            name="fk_claim_evidence_claim_id_claims", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"],
            name="fk_claim_evidence_evidence_id_evidence", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claim_evidence"),
        sa.UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_claim_id_evidence_id"),
        sa.CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 1)", name="ck_claim_evidence_weight_range"
        ),
    )
    op.create_index("ix_claim_evidence_organization_id", "claim_evidence", ["organization_id"])
    op.create_index("ix_claim_evidence_claim_id", "claim_evidence", ["claim_id"])
    op.create_index("ix_claim_evidence_evidence_id", "claim_evidence", ["evidence_id"])


def downgrade() -> None:
    op.drop_index("ix_claim_evidence_evidence_id", table_name="claim_evidence")
    op.drop_index("ix_claim_evidence_claim_id", table_name="claim_evidence")
    op.drop_index("ix_claim_evidence_organization_id", table_name="claim_evidence")
    op.drop_table("claim_evidence")

    op.drop_index("ix_evidence_study_type", table_name="evidence")
    op.drop_index("ix_evidence_document_chunk_id", table_name="evidence")
    op.drop_index("ix_evidence_document_id", table_name="evidence")
    op.drop_index("ix_evidence_source_id", table_name="evidence")
    op.drop_index("ix_evidence_organization_id", table_name="evidence")
    op.drop_table("evidence")

    bind = op.get_bind()
    postgresql.ENUM(name="evidence_relation").drop(bind, checkfirst=True)
    postgresql.ENUM(name="evidence_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="evidence_strength").drop(bind, checkfirst=True)
    postgresql.ENUM(name="evidence_directness").drop(bind, checkfirst=True)
