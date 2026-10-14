"""sources, documents, document_chunks + deferred relationships.source_id FK

Revision ID: 0004
Revises: 0003
Create Date: 2026-01-04 00:00:00

Phase 3: Sources -> Documents -> DocumentChunks (with pgvector
embeddings), plus adding the foreign key on relationships.source_id
that Phase 2's migration deliberately left off (the `sources` table
didn't exist yet at that point — see app/models/relationship.py).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.core.config import settings

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    source_access_status = postgresql.ENUM(
        "unknown", "accessible", "paywalled", "restricted", "unavailable",
        name="source_access_status", create_type=False,
    )
    source_rights_status = postgresql.ENUM(
        "unknown", "open", "licensed", "restricted", "proprietary",
        name="source_rights_status", create_type=False,
    )
    document_extraction_status = postgresql.ENUM(
        "pending", "extracting", "extracted", "failed",
        name="document_extraction_status", create_type=False,
    )

    source_access_status.create(bind, checkfirst=True)
    source_rights_status.create(bind, checkfirst=True)
    document_extraction_status.create(bind, checkfirst=True)

    # --- sources ---------------------------------------------------
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("pmid", sa.String(length=50), nullable=True),
        sa.Column("isbn", sa.String(length=50), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("access_status", source_access_status, nullable=False, server_default="unknown"),
        sa.Column("rights_status", source_rights_status, nullable=False, server_default="unknown"),
        sa.Column("reliability_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_sources_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.CheckConstraint(
            "reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 1)",
            name="ck_sources_reliability_score_range",
        ),
    )
    op.create_index("ix_sources_organization_id", "sources", ["organization_id"])
    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_index("ix_sources_url", "sources", ["url"])
    op.create_index("ix_sources_doi", "sources", ["doi"])
    op.create_index("ix_sources_pmid", "sources", ["pmid"])

    # --- documents ---------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("mime_type", sa.String(length=100), nullable=False, server_default="text/plain"),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("storage_path", sa.String(length=1000), nullable=True),
        sa.Column("extraction_status", document_extraction_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_documents_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"],
            name="fk_documents_source_id_sources", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])

    # --- document_chunks -----------------------------------------------
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(settings.EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_document_chunks_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name="fk_document_chunks_document_id_documents", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_chunk_index"
        ),
    )
    op.create_index("ix_document_chunks_organization_id", "document_chunks", ["organization_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    # HNSW index for cosine-distance nearest-neighbor search (master spec
    # section 53: "Use HNSW or appropriate pgvector index for
    # embeddings"). SQLAlchemy/Alembic have no native `op.create_index`
    # support for pgvector's access-method-specific index options, so
    # this is raw DDL. `vector_cosine_ops` matches the `.cosine_distance()`
    # operator used in app/services/document_chunk_service.py — an HNSW
    # index built with a different ops class would silently not be used
    # by a query using a different distance operator.
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw_cosine "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )

    # --- deferred FK from Phase 2: relationships.source_id -> sources.id ---
    op.create_foreign_key(
        "fk_relationships_source_id_sources",
        "relationships", "sources",
        ["source_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_relationships_source_id_sources", "relationships", type_="foreignkey")

    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw_cosine")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_organization_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_index("ix_documents_source_id", table_name="documents")
    op.drop_index("ix_documents_organization_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_sources_pmid", table_name="sources")
    op.drop_index("ix_sources_doi", table_name="sources")
    op.drop_index("ix_sources_url", table_name="sources")
    op.drop_index("ix_sources_source_type", table_name="sources")
    op.drop_index("ix_sources_organization_id", table_name="sources")
    op.drop_table("sources")

    bind = op.get_bind()
    postgresql.ENUM(name="document_extraction_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="source_rights_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="source_access_status").drop(bind, checkfirst=True)
