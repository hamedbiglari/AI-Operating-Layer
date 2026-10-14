"""document_conversions, document_tables, document_assets (Phase 3 completion)

Revision ID: 0013
Revises: 0012
Create Date: 2026-01-13 00:00:00

Document Intelligence persistence (ADR-065, ADR-066).

`documents` gains UNIQUE (id, organization_id) so the three new tables can
carry composite tenant FKs (ADR-037). Semantically a no-op - id is already
unique - and it is what lets the database refuse a cross-tenant artifact
rather than relying on service code to remember.

No prior migration is modified.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    conversion_status = postgresql.ENUM(
        "pending", "succeeded", "empty", "unsupported", "failed",
        name="document_conversion_status", create_type=False)
    extraction_level = postgresql.ENUM(
        "1", "2", "3", "4", name="document_extraction_level", create_type=False)
    asset_status = postgresql.ENUM(
        "detected_not_extracted", "extracted", "failed",
        name="document_asset_status", create_type=False)
    ocr_status = postgresql.ENUM(
        "not_attempted", "succeeded", "no_text_found", "unavailable", "failed",
        name="document_ocr_status", create_type=False)
    for t in (conversion_status, extraction_level, asset_status, ocr_status):
        t.create(bind, checkfirst=True)

    op.create_unique_constraint(
        "uq_documents_id_organization_id", "documents", ["id", "organization_id"]
    )

    op.create_table(
        "document_conversions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_mime_type", sa.String(length=120), nullable=True),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=True),
        sa.Column("converter_name", sa.String(length=80), nullable=False),
        sa.Column("converter_version", sa.String(length=40), nullable=False),
        sa.Column("conversion_options", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("conversion_status", conversion_status, nullable=False, server_default="pending"),
        sa.Column("conversion_error", sa.String(length=500), nullable=True),
        sa.Column("conversion_duration_seconds", sa.Float(), nullable=True),
        sa.Column("extraction_level", extraction_level, nullable=False, server_default="1"),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("output_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("table_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_engine", sa.String(length=80), nullable=True),
        sa.Column("ocr_version", sa.String(length=80), nullable=True),
        sa.Column("vision_model", sa.String(length=120), nullable=True),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_document_conversions_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            name="fk_document_conversions_document_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_document_conversions"),
    )
    for col in ("organization_id", "document_id", "source_hash", "conversion_status"):
        op.create_index(f"ix_document_conversions_{col}", "document_conversions", [col])

    op.create_table(
        "document_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("headers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("rows", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("extraction_strategy", sa.String(length=40), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_document_tables_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            name="fk_document_tables_document_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_document_tables"),
    )
    for col in ("organization_id", "document_id"):
        op.create_index(f"ix_document_tables_{col}", "document_tables", [col])

    op.create_table(
        "document_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", sa.String(length=300), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("storage_path", sa.String(length=1000), nullable=True),
        sa.Column("status", asset_status, nullable=False, server_default="detected_not_extracted"),
        sa.Column("ocr_status", ocr_status, nullable=False, server_default="not_attempted"),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("ocr_engine", sa.String(length=80), nullable=True),
        sa.Column("ocr_version", sa.String(length=80), nullable=True),
        sa.Column("vision_model", sa.String(length=120), nullable=True),
        sa.Column("vision_description", sa.Text(), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_document_assets_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            name="fk_document_assets_document_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_document_assets"),
    )
    for col in ("organization_id", "document_id", "source_hash", "ocr_status"):
        op.create_index(f"ix_document_assets_{col}", "document_assets", [col])


def downgrade() -> None:
    for col in ("ocr_status", "source_hash", "document_id", "organization_id"):
        op.drop_index(f"ix_document_assets_{col}", table_name="document_assets")
    op.drop_table("document_assets")
    for col in ("document_id", "organization_id"):
        op.drop_index(f"ix_document_tables_{col}", table_name="document_tables")
    op.drop_table("document_tables")
    for col in ("conversion_status", "source_hash", "document_id", "organization_id"):
        op.drop_index(f"ix_document_conversions_{col}", table_name="document_conversions")
    op.drop_table("document_conversions")

    op.drop_constraint("uq_documents_id_organization_id", "documents", type_="unique")

    bind = op.get_bind()
    for name in ("document_ocr_status", "document_asset_status",
                 "document_extraction_level", "document_conversion_status"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
