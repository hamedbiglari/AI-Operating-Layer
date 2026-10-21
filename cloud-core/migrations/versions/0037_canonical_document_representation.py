"""Canonical Document Representation, differentiated confidence, extraction history, evidence location,
and the `completed_with_failures` AI-job state (prompt v4.0; ADR-122, ADR-123). Additive and reversible.

* `document_elements` — the persisted CDR, one set per extraction attempt.
* `document_conversions` gains the layout provider, six confidence figures, processing state, review
  flags, candidates, `is_current`/`superseded_at` history. Existing rows become `is_current = true`
  with `processing_state = 'processed'` if they succeeded (they were the only extraction there was) —
  their confidence stays NULL ("not measured"), never back-filled with a guess.
* `document_tables` / `document_assets` gain `conversion_id` (NULL for rows written before this).
* `evidence` gains `document_element_id`, `page_number`, `location`.
* `ai_jobs.status` admits `completed_with_failures` (v4 §66: a job whose items failed is not complete).

Revision ID: 0037
Revises: 0036
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()

PROCESSING_STATES = ("queued", "processing", "partially_processed", "processed", "failed", "retrying",
                     "needs_review", "completed")
_OLD_JOB = "('queued', 'running', 'paused', 'pause_requested', 'blocked', 'completed', 'cancelled', 'cancel_requested')"
_NEW_JOB = ("('queued', 'running', 'paused', 'pause_requested', 'blocked', 'completed', "
            "'completed_with_failures', 'cancelled', 'cancel_requested')")


def upgrade() -> None:
    # ---- document_conversions: v4 columns
    add = lambda name, type_, **kw: op.add_column("document_conversions", sa.Column(name, type_, **kw))  # noqa: E731
    add("layout_provider", sa.String(60), nullable=True)
    add("layout_provider_version", sa.String(80), nullable=True)
    add("provider_config", JSONB, nullable=False, server_default="{}")
    add("cdr_schema_version", sa.Integer(), nullable=True)
    add("document_class", sa.String(20), nullable=True)
    for dim in ("text", "layout", "table", "equation", "figure", "overall"):
        add(f"{dim}_confidence", sa.Float(), nullable=True)
    add("processing_state", sa.String(30), nullable=False, server_default="queued")
    add("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    add("review_reasons", JSONB, nullable=False, server_default="[]")
    add("unprocessed_pages", JSONB, nullable=False, server_default="[]")
    add("candidates", JSONB, nullable=False, server_default="[]")
    add("provider_raw_output", sa.Text(), nullable=True)
    add("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    add("superseded_at", sa.TIMESTAMP(timezone=True), nullable=True)
    add("trigger", sa.String(40), nullable=False, server_default="upload")
    op.create_index("ix_document_conversions_layout_provider", "document_conversions", ["layout_provider"])
    op.create_index("ix_document_conversions_processing_state", "document_conversions", ["processing_state"])
    op.create_index("ix_document_conversions_is_current", "document_conversions", ["is_current"])
    op.create_check_constraint(
        "processing_state", "document_conversions",
        "processing_state IN (" + ", ".join(f"'{s}'" for s in PROCESSING_STATES) + ")")
    op.create_check_constraint("a_flag_needs_a_reason", "document_conversions",
                               "NOT needs_review OR jsonb_array_length(review_reasons) > 0")
    op.create_check_constraint("superseded_is_not_current", "document_conversions",
                               "superseded_at IS NULL OR NOT is_current")
    # Back-fill the state of what already exists from what is actually known — nothing more.
    op.execute("UPDATE document_conversions SET processing_state = CASE conversion_status "
               "WHEN 'succeeded' THEN 'processed' WHEN 'pending' THEN 'queued' ELSE 'failed' END")
    # Only one current extraction per document: before this, the newest one was the one in use.
    op.execute("""
        UPDATE document_conversions c SET is_current = false, superseded_at = now()
        WHERE EXISTS (SELECT 1 FROM document_conversions n
                      WHERE n.document_id = c.document_id AND n.created_at > c.created_at)
    """)
    op.create_index("uq_document_conversions_one_current", "document_conversions", ["document_id"],
                    unique=True, postgresql_where=sa.text("is_current"))

    # ---- document_elements
    op.create_table(
        "document_elements",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("conversion_id", UUID, sa.ForeignKey("document_conversions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("element_type", sa.String(30), nullable=False),
        sa.Column("reading_order", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("block_id", sa.String(120), nullable=False),
        sa.Column("parent_block_id", sa.String(120), nullable=True),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("script", sa.String(20), nullable=True),
        sa.Column("direction", sa.String(3), nullable=True),
        sa.Column("bbox", JSONB, nullable=True),
        sa.Column("lines", JSONB, nullable=False, server_default="[]"),
        sa.Column("attributes", JSONB, nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("method", sa.String(60), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id", "organization_id"], ["documents.id", "documents.organization_id"],
                                name="fk_document_elements_document_organization", ondelete="CASCADE"),
        sa.UniqueConstraint("conversion_id", "reading_order", name="uq_document_elements_order"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                           name="confidence_in_range"),
        sa.CheckConstraint("page IS NULL OR page >= 1", name="page_positive"),
    )
    for col in ("organization_id", "document_id", "conversion_id", "element_type"):
        op.create_index(f"ix_document_elements_{col}", "document_elements", [col])
    op.create_index("ix_document_elements_doc_page", "document_elements", ["document_id", "page"])

    # ---- tables/assets: which extraction produced them
    for table in ("document_tables", "document_assets"):
        op.add_column(table, sa.Column("conversion_id", UUID, nullable=True))
        op.create_foreign_key(f"fk_{table}_conversion_id_document_conversions", table, "document_conversions",
                              ["conversion_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"ix_{table}_conversion_id", table, ["conversion_id"])

    # ---- evidence location
    op.add_column("evidence", sa.Column("document_element_id", UUID, nullable=True))
    op.add_column("evidence", sa.Column("page_number", sa.Integer(), nullable=True))
    op.add_column("evidence", sa.Column("location", JSONB, nullable=True))
    op.create_foreign_key("fk_evidence_document_element_id_document_elements", "evidence", "document_elements",
                          ["document_element_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_evidence_document_element_id", "evidence", ["document_element_id"])
    op.create_index("ix_evidence_page_number", "evidence", ["page_number"])

    # ---- ai_jobs: a job with failed items is not complete
    # raw SQL: op.drop_constraint would re-apply the naming convention and look for ck_ai_jobs_ck_ai_jobs_status
    op.execute("ALTER TABLE ai_jobs DROP CONSTRAINT ck_ai_jobs_status")
    op.execute(f"ALTER TABLE ai_jobs ADD CONSTRAINT ck_ai_jobs_status CHECK (status IN {_NEW_JOB})")


def downgrade() -> None:
    op.execute("UPDATE ai_jobs SET status = 'completed' WHERE status = 'completed_with_failures'")
    op.execute("ALTER TABLE ai_jobs DROP CONSTRAINT ck_ai_jobs_status")
    op.execute(f"ALTER TABLE ai_jobs ADD CONSTRAINT ck_ai_jobs_status CHECK (status IN {_OLD_JOB})")

    op.drop_index("ix_evidence_page_number", table_name="evidence")
    op.drop_index("ix_evidence_document_element_id", table_name="evidence")
    op.drop_constraint("fk_evidence_document_element_id_document_elements", "evidence", type_="foreignkey")
    for col in ("location", "page_number", "document_element_id"):
        op.drop_column("evidence", col)

    for table in ("document_assets", "document_tables"):
        op.drop_index(f"ix_{table}_conversion_id", table_name=table)
        op.drop_constraint(f"fk_{table}_conversion_id_document_conversions", table, type_="foreignkey")
        op.drop_column(table, "conversion_id")

    op.drop_table("document_elements")

    op.drop_index("uq_document_conversions_one_current", table_name="document_conversions")
    for name in ("superseded_is_not_current", "a_flag_needs_a_reason", "processing_state"):
        op.execute(f"ALTER TABLE document_conversions DROP CONSTRAINT ck_document_conversions_{name}")
    for idx in ("is_current", "processing_state", "layout_provider"):
        op.drop_index(f"ix_document_conversions_{idx}", table_name="document_conversions")
    for col in ("trigger", "superseded_at", "is_current", "provider_raw_output", "candidates", "unprocessed_pages",
                "review_reasons", "needs_review", "processing_state", "overall_confidence", "figure_confidence",
                "equation_confidence", "table_confidence", "layout_confidence", "text_confidence",
                "document_class", "cdr_schema_version", "provider_config", "layout_provider_version",
                "layout_provider"):
        op.drop_column("document_conversions", col)
